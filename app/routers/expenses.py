from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user_id
from app.schemas.expenses import ExpenseCreate, ExpenseRead
from app.services import expense_service
from app.services.errors import DomainError, NotFoundError, ValidationError

router = APIRouter(prefix="/expenses", tags=["expenses"])


def _map_error(exc: DomainError) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)


@router.post("", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def create_expense(
    body: ExpenseCreate,
    db: Session = Depends(get_db),
    caller_id: int = Depends(get_current_user_id),
) -> ExpenseRead:
    try:
        expense = expense_service.create_expense(db, caller_id=caller_id, data=body)
    except DomainError as exc:
        raise _map_error(exc) from exc
    return ExpenseRead.model_validate(expense)


@router.get("", response_model=list[ExpenseRead])
def list_expenses(
    db: Session = Depends(get_db),
    caller_id: int = Depends(get_current_user_id),
) -> list[ExpenseRead]:
    expenses = expense_service.list_expenses(db, caller_id=caller_id)
    return [ExpenseRead.model_validate(e) for e in expenses]
