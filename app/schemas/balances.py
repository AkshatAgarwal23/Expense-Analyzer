from pydantic import BaseModel, Field


class BalanceRead(BaseModel):
    user_id: int
    display_name: str
    net_paise: int = Field(
        description="Positive = they owe you; negative = you owe them"
    )
