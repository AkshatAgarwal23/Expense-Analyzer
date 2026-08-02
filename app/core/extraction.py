"""Deterministic expense extraction pre-pass.

Rules first: amount, split cues, and category keywords before any LLM call.
Amounts spoken as rupees become integer paise (400 → 40000).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# Rupee amount: optional symbol/word, digits, optional decimal, optional "ka"/"rs"/etc.
_AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d{1,2})?)\s*(?:rs\.?|rupees?|inr|ka)?",
    re.IGNORECASE,
)

# Romanized Hindi number words (Hinglish / Sarvam translit).
_ONES: dict[str, int] = {
    "ek": 1,
    "do": 2,
    "teen": 3,
    "char": 4,
    "chaar": 4,
    "paanch": 5,
    "panch": 5,
    "che": 6,
    "chhe": 6,
    "saat": 7,
    "aath": 8,
    "ath": 8,
    "nau": 9,
    "das": 10,
    "gyarah": 11,
    "barah": 12,
    "terah": 13,
    "chaudah": 14,
    "pandrah": 15,
    "solah": 16,
    "satrah": 17,
    "atharah": 18,
    "unnees": 19,
    "bees": 20,
    "ikkees": 21,
    "ikkis": 21,
    "battis": 32,
    "batisis": 32,
    "tees": 30,
    "chalis": 40,
    "pachaas": 50,
    "pachas": 50,
    "pachpan": 55,
    "pachpann": 55,
    "sattar": 70,
    "assi": 80,
    "nabbe": 90,
    # "saath" (60) also means "with" — parsed only with an explicit currency word
}

# Ambiguous: "saath" = 60 OR "with". Require rs/rupay/etc. so "mere saath" is not ₹60.
_AMBIGUOUS_ONES: dict[str, int] = {
    "saath": 60,
}

_SCALES: dict[str, int] = {
    "sau": 100,
    "hazaar": 1000,
    "hazar": 1000,
    "hazār": 1000,
    "lakh": 100_000,
    "lac": 100_000,
}

# "das hazaar", "do sau", "15 hazaar", "hazaar"
_SPOKEN_AMOUNT_RE = re.compile(
    r"\b(?:(\d+)|([a-zā]+))\s+"
    r"(hazaar|hazar|hazār|sau|lakh|lac)\b"
    r"|\b(hazaar|hazar|hazār|lakh|lac)\b",
    re.IGNORECASE,
)

# Bare spoken number near a rupee word: "pachaas rupay", "bees rs"
_SPOKEN_ONES_RUPEE_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in sorted(_ONES, key=len, reverse=True)) + r")\b"
    r"\s*(?:rs\.?|rupees?|rupaye?|rupay|inr|ka)?\b",
    re.IGNORECASE,
)

# "saath rs" / "saath rupay" = ₹60. Currency REQUIRED so "mere saath" is not an amount.
_SAATH_RUPEE_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in sorted(_AMBIGUOUS_ONES, key=len, reverse=True)) + r")\b"
    r"\s*(?:rs\.?|rupees?|rupaye?|rupay|inr)\b",
    re.IGNORECASE,
)

# Split intent: explicit words, or "X ke saath" / "with X" (not bare "saath",
# which also means "together" / "60" and false-positives solo spends).
_SPLIT_CUES = re.compile(
    r"\b(split|divide|share|baarabar|barabar|equal)\b"
    r"|\bke\s+saath\b"
    r"|\bwith\b",
    re.IGNORECASE,
)

# Keyword → seeded category name (order matters: first match wins).
# Prefer specific spend types before generic Food.
_CATEGORY_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b("
            r"uber|ola|rapido|taxi|cab|auto|rickshaw|petrol|diesel|fuel|cng|"
            r"metro|bus|train|flight|airport|parking|toll|fastag|transport|"
            r"bharwaya|bharvaya|bharwaya|petrol\s*pump|fuel\s*station|"
            r"bike|scooter|car\s*service"
            r")\b",
            re.I,
        ),
        "Transport",
    ),
    (
        re.compile(
            r"\b("
            r"rent|kiraya|kiraaya|pg|flat|emi\s*house|maintenance|society\s*fee|"
            r"broker|deposit\s*room"
            r")\b",
            re.I,
        ),
        "Rent",
    ),
    (
        re.compile(
            r"\b("
            r"shopping|amazon|flipkart|myntra|ajio|meesho|mall|clothes|kapde|"
            r"shoes|jeans|shirt|order\s*kiya|online\s*order|grocery\s*except|"
            r"big\s*bazaar|reliance\s*trends|zara|h&m"
            r")\b",
            re.I,
        ),
        "Shopping",
    ),
    (
        re.compile(
            r"\b("
            r"movie|cinema|pvr|inox|netflix|spotify|party|club|pub|concert|"
            r"game|gaming|entertainment|bowling|outing|trip\s*fun|weekend\s*plan"
            r")\b",
            re.I,
        ),
        "Entertainment",
    ),
    (
        re.compile(
            r"\b("
            r"dinner|lunch|breakfast|brunch|food|khana|khaana|chai|coffee|tea|"
            r"pizza|burger|biryani|thali|swiggy|zomato|dominos|mcdonald|"
            r"restaurant|cafe|hotel\s*food|nashta|snack|snacks|ice\s*cream|"
            r"mithai|sweets|daru|beer|drinks|bar|mess|tiffin|dabba|"
            r"paneer|chicken|mutton|egg|paratha|dosa|idli"
            r")\b",
            re.I,
        ),
        "Food",
    ),
]


@dataclass
class PrepassResult:
    amount_paise: int | None = None
    wants_split: bool = False
    category_name: str | None = None
    description_hint: str | None = None
    matched_amount_raw: str | None = None
    warnings: list[str] = field(default_factory=list)


def rupees_to_paise(rupees: float) -> int:
    """Convert rupee amount to integer paise without float money storage."""
    return int(round(rupees * 100))


def _parse_spoken_rupees(text: str) -> tuple[int, str] | None:
    """Parse Hinglish amounts like 'das hazaar' → (10000, 'das hazaar')."""
    match = _SPOKEN_AMOUNT_RE.search(text)
    if match:
        if match.group(4):
            # bare scale word → 1 * scale
            scale = _SCALES[match.group(4).lower()]
            return scale, match.group(0)

        scale = _SCALES[match.group(3).lower()]
        if match.group(1):
            multiplier = int(match.group(1))
        else:
            word = match.group(2).lower()
            # "saath hazaar" = 60k; alone "saath" is not treated as amount here
            if word == "saath":
                multiplier = 60
            else:
                multiplier = _ONES.get(word)
                if multiplier is None:
                    return None
        return multiplier * scale, match.group(0).strip()

    # "saath rs" / "saath rupay" — currency required (before optional-currency ones)
    ambig = _SAATH_RUPEE_RE.search(text)
    if ambig:
        word = ambig.group(1).lower()
        value = _AMBIGUOUS_ONES.get(word)
        if value is not None:
            return value, ambig.group(0).strip()

    # "pachaas rupay" / "bees rs" — tens/ones without a scale word
    ones_match = _SPOKEN_ONES_RUPEE_RE.search(text)
    if ones_match:
        word = ones_match.group(1).lower()
        value = _ONES.get(word)
        if value is not None:
            return value, ones_match.group(0).strip()

    return None


def guess_category_name(text: str) -> str | None:
    """Return seeded category name from keyword rules, or None."""
    for pattern, category_name in _CATEGORY_KEYWORDS:
        if pattern.search(text):
            return category_name
    return None


def extract_prepass(transcript: str) -> PrepassResult:
    text = transcript.strip()
    result = PrepassResult()
    if not text:
        result.warnings.append("Empty transcript")
        return result

    amount_match = _AMOUNT_RE.search(text)
    if amount_match:
        raw = amount_match.group(1)
        result.matched_amount_raw = raw
        result.amount_paise = rupees_to_paise(float(raw))
    else:
        spoken = _parse_spoken_rupees(text)
        if spoken is not None:
            rupees, raw = spoken
            result.matched_amount_raw = raw
            result.amount_paise = rupees_to_paise(rupees)
        else:
            result.warnings.append("No amount found in transcript")

    result.wants_split = bool(_SPLIT_CUES.search(text))
    result.category_name = guess_category_name(text)

    cleaned = _AMOUNT_RE.sub(" ", text)
    cleaned = _SPOKEN_AMOUNT_RE.sub(" ", cleaned)
    cleaned = _SAATH_RUPEE_RE.sub(" ", cleaned)
    cleaned = _SPOKEN_ONES_RUPEE_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    if cleaned:
        result.description_hint = cleaned[:200]

    return result
