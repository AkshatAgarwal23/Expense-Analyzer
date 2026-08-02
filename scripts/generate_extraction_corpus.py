"""Generate labeled Hinglish extraction transcripts (template-composed, no paid API).

Run from repo root:
  python -m scripts.generate_extraction_corpus

Writes:
  data/extraction/corpus.jsonl
  data/extraction/train.jsonl   (80%)
  data/extraction/eval.jsonl    (20%)
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# Allow `python scripts/generate_extraction_corpus.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "extraction"
TARGET_COUNT = 1800
EVAL_RATIO = 0.20
SEED = "kharcha-extraction-v1"

FRIENDS = ["Rahul", "Priya"]

# Spoken ones / tens → rupees (matches / extends app.core.extraction._ONES).
SPOKEN_ONES: list[tuple[str, int]] = [
    ("ek", 1),
    ("do", 2),
    ("teen", 3),
    ("char", 4),
    ("chaar", 4),
    ("paanch", 5),
    ("panch", 5),
    ("che", 6),
    ("chhe", 6),
    ("saat", 7),
    ("aath", 8),
    ("ath", 8),
    ("nau", 9),
    ("das", 10),
    ("gyarah", 11),
    ("barah", 12),
    ("terah", 13),
    ("chaudah", 14),
    ("pandrah", 15),
    ("solah", 16),
    ("satrah", 17),
    ("atharah", 18),
    ("unnees", 19),
    ("bees", 20),
    ("ikkees", 21),
    ("battis", 32),
    ("tees", 30),
    ("chalis", 40),
    ("pachaas", 50),
    ("pachas", 50),
    ("pachpan", 55),
    ("saath", 60),  # only with scale or explicit rupay in templates
    ("sattar", 70),
    ("assi", 80),
    ("nabbe", 90),
]

SPOKEN_SCALE: list[tuple[str, str, int]] = [
    ("do", "sau", 200),
    ("teen", "sau", 300),
    ("paanch", "sau", 500),
    ("das", "sau", 1000),
    ("ek", "hazaar", 1000),
    ("do", "hazaar", 2000),
    ("teen", "hazaar", 3000),
    ("paanch", "hazaar", 5000),
    ("das", "hazaar", 10_000),
    ("pandrah", "hazaar", 15_000),
    ("bees", "hazaar", 20_000),
    ("saath", "hazaar", 60_000),
    ("ek", "lakh", 100_000),
    ("do", "lakh", 200_000),
]

DIGIT_AMOUNTS = [
    10, 20, 30, 40, 50, 60, 75, 80, 99, 100, 120, 150, 200, 250, 300, 350,
    400, 450, 500, 600, 750, 800, 999, 1000, 1200, 1500, 2000, 2500, 3000,
    4500, 5000, 7500, 8000, 9999, 10_000, 12_000, 15_000, 18_000, 20_000,
    25_000, 30_000, 45_000, 50_000,
]

# category → keyword phrases used in utterances
CATEGORY_PHRASES: dict[str, list[str]] = {
    "Food": [
        "chai", "coffee", "tea", "dinner", "lunch", "breakfast", "nashta",
        "pizza", "burger", "biryani", "thali", "swiggy", "zomato", "snacks",
        "ice cream", "mithai", "paratha", "dosa", "idli", "khana", "khaana",
        "restaurant", "cafe", "tiffin", "dabba", "paneer", "chicken",
        "dominos", "mcdonald", "brunch", "beer", "daru",
    ],
    "Transport": [
        "uber", "ola", "rapido", "taxi", "cab", "auto", "rickshaw", "petrol",
        "diesel", "fuel", "metro", "bus", "train", "parking", "toll",
        "fastag", "petrol pump", "bike", "scooter",
    ],
    "Rent": [
        "rent", "kiraya", "kiraaya", "pg", "flat", "maintenance",
        "society fee", "broker",
    ],
    "Shopping": [
        "shopping", "amazon", "flipkart", "myntra", "ajio", "meesho", "mall",
        "kapde", "clothes", "shoes", "jeans", "shirt", "zara",
    ],
    "Entertainment": [
        "movie", "cinema", "pvr", "inox", "netflix", "spotify", "party",
        "club", "concert", "gaming", "bowling", "outing",
    ],
    "Other": [
        "recharge", "medicine", "pharmacy", "salon", "haircut", "laundry",
        "xerox", "printout", "donation", "gift", "misc",
    ],
}

RUPEE_WORDS = ["rupay", "rupaye", "rupees", "rs", "rs.", "ka"]

SPLIT_CUES_WITH_FRIEND = [
    "{friend} ke saath",
    "with {friend}",
    "{friend} ke saath split",
    "split with {friend}",
    "{friend} se baarabar",
]


def _stable_hash(text: str) -> int:
    return int(hashlib.sha256(f"{SEED}:{text}".encode()).hexdigest(), 16)


def _pick(seq: list, key: str) -> object:
    return seq[_stable_hash(key) % len(seq)]


def _case(id_: str, transcript: str, amount_paise: int | None, category: str,
          wants_split: bool, friend_names: list[str], bucket: str) -> dict:
    return {
        "id": id_,
        "transcript": transcript,
        "amount_paise": amount_paise,
        "category_name": category,
        "wants_split": wants_split,
        "friend_names": friend_names,
        "bucket": bucket,
    }


def _digit_templates(rupees: int, phrase: str, friend: str | None) -> list[tuple[str, str]]:
    """Return (transcript, bucket_suffix) variants for a digit amount."""
    r = str(rupees)
    rw = _pick(RUPEE_WORDS, f"rw-{r}-{phrase}")
    solos = [
        (f"{r} {rw} {phrase}", "digit_solo"),
        (f"{r} {rw} ki {phrase}", "digit_solo"),
        (f"{phrase} pe {r} {rw}", "digit_solo"),
        (f"{phrase} mai {r} {rw} lagay", "digit_solo"),
        (f"{phrase} ke liye {r}", "digit_solo"),
        (f"spent {r} on {phrase}", "digit_solo"),
        (f"₹{r} {phrase}", "digit_solo"),
        (f"{r} rs {phrase}", "digit_solo"),
    ]
    if friend is None:
        return solos
    cue = _pick(SPLIT_CUES_WITH_FRIEND, f"split-{r}-{phrase}-{friend}")
    assert isinstance(cue, str)
    cue_filled = cue.format(friend=friend)
    splits = [
        (f"{r} {rw} {phrase}, {cue_filled}", "digit_split"),
        (f"{phrase} {r} {rw} {cue_filled}", "digit_split"),
        (f"{r} ka {phrase} {cue_filled}", "digit_split"),
        (f"{cue_filled} {r} {rw} {phrase}", "digit_split"),
    ]
    return splits


def _spoken_ones_templates(word: str, phrase: str, friend: str | None) -> list[tuple[str, str]]:
    rw = _pick(RUPEE_WORDS, f"srw-{word}-{phrase}")
    solos = [
        (f"{word} {rw} {phrase}", "spoken_solo"),
        (f"{word} {rw} {phrase} mai", "spoken_solo"),
        (f"{phrase} mai {word} {rw}", "spoken_solo"),
        (f"{phrase} kiya {word} {rw} lagay", "spoken_solo"),
        (f"{word} rs {phrase}", "spoken_solo"),
    ]
    if friend is None:
        return solos
    cue = _pick(SPLIT_CUES_WITH_FRIEND, f"ssplit-{word}-{phrase}-{friend}")
    assert isinstance(cue, str)
    cue_filled = cue.format(friend=friend)
    return [
        (f"{word} {rw} {phrase} {cue_filled}", "spoken_split"),
        (f"{phrase} {word} {rw} {cue_filled}", "spoken_split"),
    ]


def _spoken_scale_templates(left: str, scale: str, phrase: str, friend: str | None) -> list[tuple[str, str]]:
    solos = [
        (f"{left} {scale} ka {phrase}", "spoken_scale_solo"),
        (f"{left} {scale} {phrase}", "spoken_scale_solo"),
        (f"{phrase} {left} {scale}", "spoken_scale_solo"),
        (f"{left} {scale} rupay {phrase}", "spoken_scale_solo"),
    ]
    if friend is None:
        return solos
    cue = _pick(SPLIT_CUES_WITH_FRIEND, f"scsplit-{left}-{scale}-{phrase}-{friend}")
    assert isinstance(cue, str)
    cue_filled = cue.format(friend=friend)
    return [
        (f"{left} {scale} ka {phrase} {cue_filled}", "spoken_scale_split"),
        (f"{phrase} {left} {scale} {cue_filled}", "spoken_scale_split"),
    ]


def generate_cases() -> list[dict]:
    cases: list[dict] = []
    seen: set[str] = set()

    def add(case: dict) -> None:
        t = case["transcript"].strip().lower()
        if t in seen or not case["transcript"].strip():
            return
        seen.add(t)
        cases.append(case)

    # --- Digit amounts × categories × solo/split ---
    for cat, phrases in CATEGORY_PHRASES.items():
        for i, rupees in enumerate(DIGIT_AMOUNTS):
            phrase = phrases[i % len(phrases)]
            # solo
            for j, (transcript, bucket) in enumerate(
                _digit_templates(rupees, phrase, friend=None)
            ):
                add(_case(
                    f"{cat.lower()}-digit-solo-{rupees}-{j}",
                    transcript,
                    rupees * 100,
                    cat,
                    False,
                    [],
                    f"{bucket}_{cat.lower()}",
                ))
            # split with friend
            friend = FRIENDS[i % len(FRIENDS)]
            for j, (transcript, bucket) in enumerate(
                _digit_templates(rupees, phrase, friend=friend)
            ):
                add(_case(
                    f"{cat.lower()}-digit-split-{rupees}-{friend.lower()}-{j}",
                    transcript,
                    rupees * 100,
                    cat,
                    True,
                    [friend],
                    f"{bucket}_{cat.lower()}",
                ))

    # --- Spoken ones × categories ---
    for cat, phrases in CATEGORY_PHRASES.items():
        for i, (word, rupees) in enumerate(SPOKEN_ONES):
            # skip bare saath as amount in solo "rupay" form when we want negatives later;
            # still include saath rupay as valid amount
            phrase = phrases[i % len(phrases)]
            for j, (transcript, bucket) in enumerate(
                _spoken_ones_templates(word, phrase, friend=None)
            ):
                add(_case(
                    f"{cat.lower()}-spoken-solo-{word}-{j}",
                    transcript,
                    rupees * 100,
                    cat,
                    False,
                    [],
                    f"{bucket}_{cat.lower()}",
                ))
            friend = FRIENDS[i % len(FRIENDS)]
            for j, (transcript, bucket) in enumerate(
                _spoken_ones_templates(word, phrase, friend=friend)
            ):
                add(_case(
                    f"{cat.lower()}-spoken-split-{word}-{friend.lower()}-{j}",
                    transcript,
                    rupees * 100,
                    cat,
                    True,
                    [friend],
                    f"{bucket}_{cat.lower()}",
                ))

    # --- Spoken scale amounts ---
    for cat, phrases in CATEGORY_PHRASES.items():
        for i, (left, scale, rupees) in enumerate(SPOKEN_SCALE):
            phrase = phrases[i % len(phrases)]
            for j, (transcript, bucket) in enumerate(
                _spoken_scale_templates(left, scale, phrase, friend=None)
            ):
                add(_case(
                    f"{cat.lower()}-scale-solo-{left}-{scale}-{j}",
                    transcript,
                    rupees * 100,
                    cat,
                    False,
                    [],
                    f"{bucket}_{cat.lower()}",
                ))
            friend = FRIENDS[(i + 1) % len(FRIENDS)]
            for j, (transcript, bucket) in enumerate(
                _spoken_scale_templates(left, scale, phrase, friend=friend)
            ):
                add(_case(
                    f"{cat.lower()}-scale-split-{left}-{scale}-{friend.lower()}-{j}",
                    transcript,
                    rupees * 100,
                    cat,
                    True,
                    [friend],
                    f"{bucket}_{cat.lower()}",
                ))

    # --- Negatives: no amount ---
    no_amount = [
        # "with" / "ke saath" are split cues even without a seeded friend name
        ("dinner with friends", "Food", True, []),
        ("chai piyi Rahul ke saath", "Food", True, ["Rahul"]),
        ("uber liya kal", "Transport", False, []),
        ("movie dekhne gaye Priya ke saath", "Entertainment", True, ["Priya"]),
        ("kiraya discuss kiya", "Rent", False, []),
        ("myntra pe order kiya", "Shopping", False, []),
        ("recharge karna hai", "Other", False, []),
        ("khana khaya mere saath", "Food", False, []),  # bare saath ≠ split
        ("petrol bharwaya mere saath", "Transport", False, []),
        ("party thi sab ke saath", "Entertainment", True, []),  # ke saath cue
    ]
    for i, (transcript, cat, split, friends) in enumerate(no_amount):
        add(_case(
            f"neg-noamount-{i}",
            transcript,
            None,
            cat,
            split,
            friends,
            "no_amount",
        ))

    # Extra bare-saath negatives (must not mark wants_split)
    bare_saath = [
        "chai kiya 50 rupay mere saath",
        "lunch 200 mere saath",
        "uber 150 mere saath liya",
        "coffee 80 mere saath",
        "pizza 400 mere saath order",
    ]
    for i, transcript in enumerate(bare_saath):
        # amounts present so prepass should find them; split must be false
        amount = [50, 200, 150, 80, 400][i] * 100
        cat = ["Food", "Food", "Transport", "Food", "Food"][i]
        add(_case(
            f"neg-baresaath-{i}",
            transcript,
            amount,
            cat,
            False,
            [],
            "bare_saath_no_split",
        ))

    # Cap / pad to TARGET_COUNT with deterministic extras from digit pool
    if len(cases) > TARGET_COUNT:
        # Prefer keeping all negatives; trim from the largest digit buckets first
        negatives = [c for c in cases if c["bucket"].startswith(("no_amount", "bare_saath"))]
        rest = [c for c in cases if c not in negatives]
        rest.sort(key=lambda c: c["id"])
        keep_n = TARGET_COUNT - len(negatives)
        cases = rest[:keep_n] + negatives
    elif len(cases) < TARGET_COUNT:
        # Pad with more digit×phrase permutations
        extra_i = 0
        while len(cases) < TARGET_COUNT:
            rupees = DIGIT_AMOUNTS[extra_i % len(DIGIT_AMOUNTS)]
            cats = list(CATEGORY_PHRASES.keys())
            cat = cats[extra_i % len(cats)]
            phrases = CATEGORY_PHRASES[cat]
            phrase = phrases[(extra_i // len(cats)) % len(phrases)]
            friend = FRIENDS[extra_i % 2] if extra_i % 3 == 0 else None
            variants = _digit_templates(rupees, phrase, friend)
            transcript, bucket = variants[extra_i % len(variants)]
            add(_case(
                f"pad-{extra_i}",
                transcript,
                rupees * 100,
                cat,
                friend is not None,
                [friend] if friend else [],
                f"{bucket}_{cat.lower()}_pad",
            ))
            extra_i += 1
            if extra_i > TARGET_COUNT * 5:
                break

    cases.sort(key=lambda c: c["id"])
    return cases[:TARGET_COUNT] if len(cases) >= TARGET_COUNT else cases


def split_train_eval(cases: list[dict]) -> tuple[list[dict], list[dict]]:
    """Deterministic 80/20 split by hashing id."""
    train: list[dict] = []
    eval_rows: list[dict] = []
    for case in cases:
        # Stable bucket into eval
        h = _stable_hash(case["id"]) % 1000
        if h < int(EVAL_RATIO * 1000):
            eval_rows.append(case)
        else:
            train.append(case)
    return train, eval_rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    cases = generate_cases()
    train, eval_rows = split_train_eval(cases)
    write_jsonl(OUT_DIR / "corpus.jsonl", cases)
    write_jsonl(OUT_DIR / "train.jsonl", train)
    write_jsonl(OUT_DIR / "eval.jsonl", eval_rows)
    print(f"Wrote {len(cases)} cases -> {OUT_DIR}")
    print(f"  train={len(train)}  eval={len(eval_rows)}")
    buckets: dict[str, int] = {}
    for c in cases:
        # coarse bucket prefix
        key = c["bucket"].rsplit("_", 1)[0] if "_" in c["bucket"] else c["bucket"]
        # better: first two segments
        parts = c["bucket"].split("_")
        key = "_".join(parts[:2]) if len(parts) >= 2 else c["bucket"]
        buckets[key] = buckets.get(key, 0) + 1
    print("Bucket prefixes (sample):")
    for k in sorted(buckets)[:20]:
        print(f"  {k}: {buckets[k]}")


if __name__ == "__main__":
    main()
