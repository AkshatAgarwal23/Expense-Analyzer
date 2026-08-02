"""Build chat-JSONL for fine-tuning kharcha-extract from train.jsonl.

Run:
  python -m scripts.prepare_llm_finetune

Writes:
  data/extraction/finetune_chat.jsonl   — HuggingFace/Unsloth chat messages
  data/extraction/finetune_hard.jsonl   — hard/residual subset (weighted up)

Hard rows = no/weak prepass amount, category Other, or messy spoken amounts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.extraction import extract_prepass

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "extraction"
TRAIN = DATA / "train.jsonl"

SYSTEM_PROMPT = (
    "Extract one expense from a short Hinglish transcript. "
    "Reply with one JSON object only. Keys: amount_rupees, description, "
    "category_name, friend_names, split, spent_on. "
    "spent_on must be YYYY-MM-DD or null. Use only friend names from the Friends list."
)

FRIENDS = ["Rahul", "Priya"]
CATEGORIES = ["Food", "Transport", "Rent", "Shopping", "Entertainment", "Other"]

# Duplicate hard examples this many times in the combined chat file.
HARD_WEIGHT = 3


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _assistant_payload(row: dict) -> dict:
    amount_paise = row.get("amount_paise")
    amount_rupees = None if amount_paise is None else amount_paise / 100.0
    # Prefer integer-looking amounts without trailing .0 noise in JSON
    if amount_rupees is not None and float(amount_rupees).is_integer():
        amount_out: float | int = int(amount_rupees)
    else:
        amount_out = amount_rupees  # type: ignore[assignment]

    return {
        "amount_rupees": amount_out,
        "description": row["transcript"][:120],
        "category_name": row.get("category_name") or "Other",
        "friend_names": list(row.get("friend_names") or []),
        "split": bool(row.get("wants_split")),
        "spent_on": None,
    }


def _user_prompt(row: dict) -> str:
    pre = extract_prepass(row["transcript"])
    return (
        f"Transcript: {row['transcript']!r}\n"
        f"Hints: amount_paise={pre.amount_paise}, split={pre.wants_split}, "
        f"category={pre.category_name}\n"
        f"Friends: {FRIENDS}\n"
        f"Categories: {CATEGORIES}\n"
        f"JSON keys: amount_rupees, description, category_name, friend_names, split, spent_on"
    )


def to_chat(row: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(row)},
            {
                "role": "assistant",
                "content": json.dumps(_assistant_payload(row), ensure_ascii=False),
            },
        ],
        "meta": {
            "id": row["id"],
            "bucket": row.get("bucket"),
            "hard": is_hard(row),
        },
    }


def is_hard(row: dict) -> bool:
    pre = extract_prepass(row["transcript"])
    if row.get("amount_paise") is None:
        return True
    if pre.amount_paise is None:
        return True
    if row.get("category_name") == "Other":
        return True
    bucket = row.get("bucket") or ""
    if "spoken" in bucket or "no_amount" in bucket:
        return True
    return False


def main() -> None:
    if not TRAIN.is_file():
        print(f"Missing {TRAIN}; run: python -m scripts.generate_extraction_corpus")
        sys.exit(1)

    rows = load_jsonl(TRAIN)
    chats = [to_chat(r) for r in rows]
    hard = [c for c in chats if c["meta"]["hard"]]

    # Weighted training set: all once + hard extras
    weighted: list[dict] = list(chats)
    for _ in range(HARD_WEIGHT - 1):
        weighted.extend(hard)

    # Strip meta for the file Unsloth/HF will load (keep id optional via messages only)
    def strip_meta(c: dict) -> dict:
        return {"messages": c["messages"]}

    write_jsonl(DATA / "finetune_chat.jsonl", [strip_meta(c) for c in weighted])
    write_jsonl(DATA / "finetune_hard.jsonl", [strip_meta(c) for c in hard])

    print(f"train rows:     {len(rows)}")
    print(f"hard rows:      {len(hard)}")
    print(f"weighted chats: {len(weighted)}  (hard weight={HARD_WEIGHT})")
    print(f"wrote {DATA / 'finetune_chat.jsonl'}")
    print(f"wrote {DATA / 'finetune_hard.jsonl'}")


if __name__ == "__main__":
    main()
