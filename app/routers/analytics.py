from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user_id
from app.schemas.analytics import CategorySpendRead
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/spend-by-category", response_model=list[CategorySpendRead])
def spend_by_category(
    db: Session = Depends(get_db),
    caller_id: int = Depends(get_current_user_id),
) -> list[CategorySpendRead]:
    return analytics_service.spend_by_category(db, caller_id=caller_id)
