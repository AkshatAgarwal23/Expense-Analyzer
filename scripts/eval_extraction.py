"""Evaluate extraction prepass (and optionally live Ollama) on labeled JSONL.

Run from repo root:
  python -m scripts.eval_extraction
  python -m scripts.eval_extraction --prepass
  python -m scripts.eval_extraction --llm
  python -m scripts.eval_extraction --file data/extraction/eval.jsonl

No DB / ledger writes. --llm calls Ollama only for rows where prepass misses amount.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.extraction import extract_prepass
from app.services.extraction_service import (
    ExtractionError,
    _build_prompt,
    _call_ollama,
    _parse_llm_payload,
)

DEFAULT_FILE = Path(__file__).resolve().parents[1] / "data" / "extraction" / "eval.jsonl"
FRIEND_NAMES = ["Rahul", "Priya"]
CATEGORY_NAMES = ["Food", "Transport", "Rent", "Shopping", "Entertainment", "Other"]


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _norm_cat(name: str | None) -> str | None:
    if name is None:
        return None
    return name.strip().lower()


def eval_prepass(rows: list[dict]) -> dict:
    n = len(rows)
    amount_gold = [r for r in rows if r.get("amount_paise") is not None]
    amount_none = [r for r in rows if r.get("amount_paise") is None]

    amount_correct = 0
    amount_found = 0
    amount_false_positive = 0
    category_correct = 0
    category_scored = 0
    split_correct = 0
    failures: list[dict] = []

    for row in rows:
        pre = extract_prepass(row["transcript"])
        gold_amount = row.get("amount_paise")
        gold_cat = row.get("category_name")
        gold_split = bool(row.get("wants_split"))

        if pre.amount_paise is not None:
            amount_found += 1

        if gold_amount is None:
            if pre.amount_paise is not None:
                amount_false_positive += 1
                failures.append({
                    "id": row["id"],
                    "kind": "amount_fp",
                    "transcript": row["transcript"],
                    "gold": None,
                    "pred": pre.amount_paise,
                })
        else:
            if pre.amount_paise == gold_amount:
                amount_correct += 1
            else:
                failures.append({
                    "id": row["id"],
                    "kind": "amount_miss",
                    "transcript": row["transcript"],
                    "gold": gold_amount,
                    "pred": pre.amount_paise,
                    "bucket": row.get("bucket"),
                })

        # Category: score when gold is set and not Other (Other is often keyword-less)
        if gold_cat and gold_cat != "Other":
            category_scored += 1
            if _norm_cat(pre.category_name) == _norm_cat(gold_cat):
                category_correct += 1
            else:
                failures.append({
                    "id": row["id"],
                    "kind": "category_miss",
                    "transcript": row["transcript"],
                    "gold": gold_cat,
                    "pred": pre.category_name,
                })

        if pre.wants_split == gold_split:
            split_correct += 1
        else:
            failures.append({
                "id": row["id"],
                "kind": "split_miss",
                "transcript": row["transcript"],
                "gold": gold_split,
                "pred": pre.wants_split,
            })

    n_amount = len(amount_gold)
    llm_skip_rate = amount_found / n if n else 0.0
    # Among rows that HAVE a gold amount, how often we found the exact amount
    amount_acc = amount_correct / n_amount if n_amount else 0.0
    # Recall of "found some amount" when gold has amount
    found_when_gold = sum(
        1
        for r in amount_gold
        if extract_prepass(r["transcript"]).amount_paise is not None
    )
    amount_recall = found_when_gold / n_amount if n_amount else 0.0

    return {
        "n": n,
        "n_with_amount": n_amount,
        "n_no_amount": len(amount_none),
        "amount_exact_acc": amount_acc,
        "amount_recall": amount_recall,
        "amount_false_positives": amount_false_positive,
        "llm_skip_rate": llm_skip_rate,
        "category_acc": category_correct / category_scored if category_scored else 0.0,
        "category_scored": category_scored,
        "split_acc": split_correct / n if n else 0.0,
        "failures": failures,
    }


def eval_llm(
    rows: list[dict],
    *,
    limit: int | None = None,
    force: bool = False,
) -> dict:
    """Call Ollama on residual rows (prepass missed amount), or force on a sample."""
    if force:
        # Prefer no-amount / Other / spoken so the specialist is tested on hard cases
        ranked = sorted(
            rows,
            key=lambda r: (
                0 if r.get("amount_paise") is None else 1,
                0 if r.get("category_name") == "Other" else 1,
                0 if "spoken" in (r.get("bucket") or "") else 1,
                r["id"],
            ),
        )
        residual = ranked[: limit or 20]
    else:
        residual = [
            row
            for row in rows
            if extract_prepass(row["transcript"]).amount_paise is None
        ]
        if limit is not None:
            residual = residual[:limit]

    latencies_ms: list[float] = []
    json_ok = 0
    amount_ok = 0
    category_ok = 0
    failures: list[dict] = []

    for row in residual:
        pre = extract_prepass(row["transcript"])
        prompt = _build_prompt(
            row["transcript"],
            pre,
            friend_names=FRIEND_NAMES,
            category_names=CATEGORY_NAMES,
        )
        t0 = time.perf_counter()
        try:
            raw = _call_ollama(prompt)
            llm = _parse_llm_payload(raw)
            elapsed = (time.perf_counter() - t0) * 1000
            latencies_ms.append(elapsed)
            json_ok += 1
        except (ExtractionError, ValueError, TypeError) as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            latencies_ms.append(elapsed)
            failures.append({
                "id": row["id"],
                "kind": "llm_parse",
                "transcript": row["transcript"],
                "error": str(exc),
            })
            continue

        gold_amount = row.get("amount_paise")
        if gold_amount is None:
            if llm.amount_rupees is None:
                amount_ok += 1
            else:
                failures.append({
                    "id": row["id"],
                    "kind": "llm_amount",
                    "transcript": row["transcript"],
                    "gold": None,
                    "pred": llm.amount_rupees,
                })
        else:
            pred_paise = (
                int(round(llm.amount_rupees * 100)) if llm.amount_rupees is not None else None
            )
            if pred_paise == gold_amount:
                amount_ok += 1
            else:
                failures.append({
                    "id": row["id"],
                    "kind": "llm_amount",
                    "transcript": row["transcript"],
                    "gold": gold_amount,
                    "pred": pred_paise,
                })

        gold_cat = row.get("category_name")
        if gold_cat and _norm_cat(llm.category_name) == _norm_cat(gold_cat):
            category_ok += 1
        elif gold_cat and gold_cat != "Other":
            failures.append({
                "id": row["id"],
                "kind": "llm_category",
                "transcript": row["transcript"],
                "gold": gold_cat,
                "pred": llm.category_name,
            })

    n = len(residual)
    def pctile(xs: list[float], p: float) -> float:
        if not xs:
            return 0.0
        xs_sorted = sorted(xs)
        idx = min(len(xs_sorted) - 1, max(0, int(round(p * (len(xs_sorted) - 1)))))
        return xs_sorted[idx]

    return {
        "n_residual": n,
        "json_valid_at_1": json_ok / n if n else 0.0,
        "amount_acc": amount_ok / n if n else 0.0,
        "category_acc": category_ok / n if n else 0.0,
        "latency_p50_ms": pctile(latencies_ms, 0.50),
        "latency_p95_ms": pctile(latencies_ms, 0.95),
        "latency_mean_ms": statistics.mean(latencies_ms) if latencies_ms else 0.0,
        "failures": failures[:30],
    }


def print_prepass_report(result: dict, *, top_n: int = 15) -> None:
    print("=== Prepass eval ===")
    print(f"rows:              {result['n']}")
    print(f"with gold amount:  {result['n_with_amount']}")
    print(f"no gold amount:    {result['n_no_amount']}")
    print(f"amount exact acc:  {result['amount_exact_acc']:.1%}  (gold amount rows)")
    print(f"amount recall:     {result['amount_recall']:.1%}  (found any amount when gold has one)")
    print(f"amount FPs:        {result['amount_false_positives']}  (found amount when gold is null)")
    print(f"LLM-skip rate:     {result['llm_skip_rate']:.1%}  (% rows where prepass found amount)")
    print(f"category acc:      {result['category_acc']:.1%}  (n={result['category_scored']}, excl Other)")
    print(f"split acc:         {result['split_acc']:.1%}")

    by_kind = Counter(f["kind"] for f in result["failures"])
    print("\nFailure counts:")
    for kind, count in by_kind.most_common():
        print(f"  {kind}: {count}")

    amount_misses = [f for f in result["failures"] if f["kind"] == "amount_miss"]
    print(f"\nTop amount misses (up to {top_n}):")
    for f in amount_misses[:top_n]:
        print(f"  [{f['id']}] gold={f['gold']} pred={f['pred']}  {f['transcript']!r}")

    cat_misses = [f for f in result["failures"] if f["kind"] == "category_miss"]
    print(f"\nTop category misses (up to {top_n}):")
    for f in cat_misses[:top_n]:
        print(f"  [{f['id']}] gold={f['gold']} pred={f['pred']}  {f['transcript']!r}")


def print_llm_report(result: dict) -> None:
    print("\n=== LLM residual eval ===")
    print(f"residual rows:     {result['n_residual']}")
    print(f"JSON valid @1:     {result['json_valid_at_1']:.1%}")
    print(f"amount acc:        {result['amount_acc']:.1%}")
    print(f"category acc:      {result['category_acc']:.1%}")
    print(f"latency p50 ms:    {result['latency_p50_ms']:.0f}")
    print(f"latency p95 ms:    {result['latency_p95_ms']:.0f}")
    print(f"latency mean ms:   {result['latency_mean_ms']:.0f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval extraction corpus")
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_FILE,
        help="JSONL path (default: data/extraction/eval.jsonl)",
    )
    parser.add_argument("--prepass", action="store_true", default=True,
                        help="Run prepass metrics (default)")
    parser.add_argument("--no-prepass", action="store_true", help="Skip prepass")
    parser.add_argument("--llm", action="store_true", help="Eval live Ollama on residual rows")
    parser.add_argument(
        "--llm-force",
        action="store_true",
        help="Force LLM calls on a hard sample (ignore skip), for latency comparison",
    )
    parser.add_argument("--llm-limit", type=int, default=None,
                        help="Max residual/forced rows for --llm")
    parser.add_argument("--top", type=int, default=15, help="Failure samples to print")
    args = parser.parse_args()

    rows = load_jsonl(args.file)
    if not rows:
        print(f"No rows in {args.file}", file=sys.stderr)
        sys.exit(1)

    if not args.no_prepass:
        result = eval_prepass(rows)
        print_prepass_report(result, top_n=args.top)

    if args.llm or args.llm_force:
        from app.config import settings

        print(f"\nOLLAMA_MODEL={settings.ollama_model}")
        llm_result = eval_llm(
            rows,
            limit=args.llm_limit if args.llm_limit is not None else (20 if args.llm_force else None),
            force=args.llm_force,
        )
        print_llm_report(llm_result)


if __name__ == "__main__":
    main()
