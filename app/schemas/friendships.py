from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class FriendshipStatusRead(str, Enum):
    pending = "pending"
    accepted = "accepted"


class FriendshipCreate(BaseModel):
    user_id: int = Field(ge=1)


class FriendshipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_a_id: int
    user_b_id: int
    user_a_display_name: str
    user_b_display_name: str
    requested_by_id: int
    status: FriendshipStatusRead
    created_at: datetime
