from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user_id
from app.models import User
from app.schemas.users import UserRead

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserRead)
def read_me(
    db: Session = Depends(get_db),
    caller_id: int = Depends(get_current_user_id),
) -> User:
    """Return the caller resolved via X-User-Id (stands in for JWT until auth lands)."""
    user = db.get(User, caller_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {caller_id} not found",
        )
    return user
