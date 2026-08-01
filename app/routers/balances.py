from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user_id
from app.schemas.balances import BalanceRead
from app.services import balance_service

router = APIRouter(prefix="/balances", tags=["balances"])


@router.get("/v1", response_model=list[BalanceRead])
def list_balances(
    db: Session = Depends(get_db),
    caller_id: int = Depends(get_current_user_id),
) -> list[BalanceRead]:
    return balance_service.get_balances(db, caller_id=caller_id)

@router.get("/v2", response_model=list[BalanceRead])
def list_balances(
    db: Session = Depends(get_db),
    caller_id: int = Depends(get_current_user_id),
) -> list[BalanceRead]:
    return balance_service.get_balances(db, caller_id=caller_id)