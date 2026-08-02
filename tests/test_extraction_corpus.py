"""Regression floor: prepass accuracy on data/extraction/eval.jsonl."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.extraction import extract_prepass

EVAL_PATH = Path(__file__).resolve().parents[1] / "data" / "extraction" / "eval.jsonl"

# Floors after rules expansion — keep CI green without Ollama.
AMOUNT_EXACT_FLOOR = 0.95
AMOUNT_RECALL_FLOOR = 0.95
CATEGORY_FLOOR = 0.85
SPLIT_FLOOR = 0.95


def _load_eval() -> list[dict]:
    if not EVAL_PATH.is_file():
        pytest.skip(f"Missing {EVAL_PATH}; run: python -m scripts.generate_extraction_corpus")
    rows: list[dict] = []
    with EVAL_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


@pytest.fixture(scope="module")
def eval_rows() -> list[dict]:
    return _load_eval()


class TestExtractionCorpusPrepass:
    def test_eval_file_nonempty(self, eval_rows: list[dict]) -> None:
        assert len(eval_rows) >= 200

    def test_amount_exact_accuracy(self, eval_rows: list[dict]) -> None:
        gold = [r for r in eval_rows if r.get("amount_paise") is not None]
        assert gold
        correct = sum(
            1
            for r in gold
            if extract_prepass(r["transcript"]).amount_paise == r["amount_paise"]
        )
        acc = correct / len(gold)
        assert acc >= AMOUNT_EXACT_FLOOR, f"amount exact acc {acc:.1%} < {AMOUNT_EXACT_FLOOR:.0%}"

    def test_amount_recall(self, eval_rows: list[dict]) -> None:
        gold = [r for r in eval_rows if r.get("amount_paise") is not None]
        found = sum(
            1
            for r in gold
            if extract_prepass(r["transcript"]).amount_paise is not None
        )
        recall = found / len(gold)
        assert recall >= AMOUNT_RECALL_FLOOR, f"amount recall {recall:.1%} < {AMOUNT_RECALL_FLOOR:.0%}"

    def test_category_accuracy_excl_other(self, eval_rows: list[dict]) -> None:
        scored = [
            r
            for r in eval_rows
            if r.get("category_name") and r["category_name"] != "Other"
        ]
        assert scored
        correct = 0
        for r in scored:
            pred = extract_prepass(r["transcript"]).category_name
            if pred and pred.lower() == r["category_name"].lower():
                correct += 1
        acc = correct / len(scored)
        assert acc >= CATEGORY_FLOOR, f"category acc {acc:.1%} < {CATEGORY_FLOOR:.0%}"

    def test_split_accuracy(self, eval_rows: list[dict]) -> None:
        correct = sum(
            1
            for r in eval_rows
            if extract_prepass(r["transcript"]).wants_split == bool(r.get("wants_split"))
        )
        acc = correct / len(eval_rows)
        assert acc >= SPLIT_FLOOR, f"split acc {acc:.1%} < {SPLIT_FLOOR:.0%}"

    def test_digit_and_spoken_buckets_amount_floor(self, eval_rows: list[dict]) -> None:
        """Buckets we claim to support must stay highly accurate."""
        supported = [
            r
            for r in eval_rows
            if r.get("amount_paise") is not None
            and (
                r.get("bucket", "").startswith("digit_")
                or r.get("bucket", "").startswith("spoken_")
            )
        ]
        assert len(supported) >= 50
        correct = sum(
            1
            for r in supported
            if extract_prepass(r["transcript"]).amount_paise == r["amount_paise"]
        )
        acc = correct / len(supported)
        assert acc >= 0.95, f"supported-bucket amount acc {acc:.1%} < 95%"
