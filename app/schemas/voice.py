from datetime import date
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models import ExpenseSource
from app.schemas.expenses import SplitMode


def _is_iso_date(text: str) -> bool:
    """YYYY-MM-DD only — rejects free text the model stuffs into spent_on."""
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", text))


class TranscriptResponse(BaseModel):
    transcript: str


class TranscriptRequest(BaseModel):
    transcript: str = Field(min_length=1)


class PrepassRead(BaseModel):
    amount_paise: int | None = None
    wants_split: bool = False
    category_name: str | None = None
    description_hint: str | None = None
    matched_amount_raw: str | None = None
    warnings: list[str] = Field(default_factory=list)


class LlmExpensePayload(BaseModel):
    """Strict JSON shape expected from Ollama before ID resolution."""

    amount_rupees: float | None = None
    description: str = ""
    category_name: str | None = None
    friend_names: list[str] = Field(default_factory=list)
    split: bool = False
    spent_on: date | None = None

    @field_validator("spent_on", mode="before")
    @classmethod
    def _coerce_spent_on(cls, value: Any) -> Any:
        # Models often dump the whole transcript into spent_on — treat junk as null.
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            text = value.strip()
            if _is_iso_date(text):
                return text
            return None
        return None

    @field_validator("amount_rupees", mode="before")
    @classmethod
    def _coerce_amount(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            cleaned = value.strip().replace(",", "")
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    @field_validator("friend_names", mode="before")
    @classmethod
    def _coerce_friends(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            return [str(v) for v in value if str(v).strip()]
        return []

    @field_validator("split", mode="before")
    @classmethod
    def _coerce_split(cls, value: Any) -> Any:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "yes", "1", "split"}
        return bool(value)


class ExpenseDraft(BaseModel):
    """Editable draft shown to the user — not written until /voice/confirm."""

    amount_paise: int = Field(ge=0)
    category_id: int
    description: str = ""
    spent_on: date
    participant_ids: list[int] = Field(default_factory=list)
    payer_id: int | None = None
    split_mode: SplitMode = SplitMode.equal
    shares: dict[int, int] | None = None
    source: ExpenseSource = ExpenseSource.voice
    transcript: str = ""
    warnings: list[str] = Field(default_factory=list)


class ExtractResponse(BaseModel):
    draft: ExpenseDraft
    prepass: PrepassRead
