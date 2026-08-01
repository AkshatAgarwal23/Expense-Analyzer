from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user_id
from app.schemas.categories import CategoryRead
from app.services import category_service

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead])
def list_categories(
    db: Session = Depends(get_db),
    caller_id: int = Depends(get_current_user_id),
) -> list[CategoryRead]:
    cats = category_service.list_categories(db, caller_id=caller_id)
    return [CategoryRead.model_validate(c) for c in cats]
