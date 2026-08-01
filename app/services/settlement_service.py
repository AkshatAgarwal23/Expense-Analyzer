from sqlalchemy.orm import Session

from app.models import Settlement, User
from app.schemas.settlements import SettlementCreate
from app.services.errors import NotFoundError, ValidationError
from app.services.friendship_service import require_accepted_friendship


def create_settlement(
    db: Session, *, caller_id: int, data: SettlementCreate
) -> Settlement:
    if data.to_user_id == caller_id:
        raise ValidationError("Cannot settle with yourself")

    to_user = db.get(User, data.to_user_id)
    if to_user is None:
        raise NotFoundError(f"user {data.to_user_id} not found")

    require_accepted_friendship(db, user_id_1=caller_id, user_id_2=data.to_user_id)

    settlement = Settlement(
        from_user_id=caller_id,
        to_user_id=data.to_user_id,
        amount_paise=data.amount_paise,
        settled_on=data.settled_on,
    )
    db.add(settlement)
    db.commit()
    db.refresh(settlement)
    return settlement
