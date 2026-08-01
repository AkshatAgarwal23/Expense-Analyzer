from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SettlementCreate(BaseModel):
    to_user_id: int = Field(ge=1)
    amount_paise: int = Field(gt=0)
    settled_on: date


class SettlementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_user_id: int
    to_user_id: int
    amount_paise: int
    settled_on: date
    created_at: datetime
