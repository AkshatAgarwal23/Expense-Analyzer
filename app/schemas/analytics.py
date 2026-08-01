from pydantic import BaseModel, Field


class CategorySpendRead(BaseModel):
    category_id: int
    category_name: str
    total_paise: int = Field(description="Sum of caller's share owed_paise in this category")
