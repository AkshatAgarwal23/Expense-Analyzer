from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user_id
from app.schemas.settlements import SettlementCreate, SettlementRead
from app.services import settlement_service
from app.services.errors import DomainError, NotFoundError, ValidationError

router = APIRouter(prefix="/settlements", tags=["settlements"])


def _map_error(exc: DomainError) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)


@router.post("", response_model=SettlementRead, status_code=status.HTTP_201_CREATED)
def create_settlement(
    body: SettlementCreate,
    db: Session = Depends(get_db),
    caller_id: int = Depends(get_current_user_id),
) -> SettlementRead:
    try:
        settlement = settlement_service.create_settlement(
            db, caller_id=caller_id, data=body
        )
    except DomainError as exc:
        raise _map_error(exc) from exc
    return SettlementRead.model_validate(settlement)
