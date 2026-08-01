from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models import ExpenseSource


class SplitMode(str, Enum):
    equal = "equal"
    exact = "exact"
    percentage = "percentage"


class ExpenseShareRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    owed_paise: int


class ExpenseCreate(BaseModel):
    amount_paise: int = Field(ge=0)
    category_id: int
    description: str = ""
    spent_on: date
    participant_ids: list[int] | None = None
    payer_id: int | None = None
    split_mode: SplitMode = SplitMode.equal
    # For exact: user_id → owed_paise. For percentage: user_id → percent (sum 100).
    shares: dict[int, int] | None = None
    source: ExpenseSource = ExpenseSource.manual


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount_paise: int
    payer_id: int
    category_id: int
    description: str
    spent_on: date
    source: str
    created_at: datetime
    shares: list[ExpenseShareRead]
