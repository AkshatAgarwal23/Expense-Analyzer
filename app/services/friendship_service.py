from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.friendships import ordered_pair
from app.models import Friendship, FriendshipStatus, User
from app.services.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError


def create_friendship(
    db: Session, *, caller_id: int, other_user_id: int
) -> Friendship:
    if caller_id == other_user_id:
        raise ValidationError("Cannot friend yourself")

    other = db.get(User, other_user_id)
    if other is None:
        raise NotFoundError(f"user {other_user_id} not found")

    user_a_id, user_b_id = ordered_pair(caller_id, other_user_id)
    existing = db.scalar(
        select(Friendship).where(
            Friendship.user_a_id == user_a_id,
            Friendship.user_b_id == user_b_id,
        )
    )
    if existing is not None:
        raise ConflictError("Friendship already exists")

    friendship = Friendship(
        user_a_id=user_a_id,
        user_b_id=user_b_id,
        requested_by_id=caller_id,
        status=FriendshipStatus.pending,
    )
    db.add(friendship)
    db.commit()
    db.refresh(friendship)
    return friendship


def accept_friendship(
    db: Session, *, caller_id: int, friendship_id: int
) -> Friendship:
    friendship = db.get(Friendship, friendship_id)
    if friendship is None:
        raise NotFoundError(f"friendship {friendship_id} not found")

    if caller_id not in (friendship.user_a_id, friendship.user_b_id):
        raise ForbiddenError("Not a party to this friendship")

    # Only the non-requester may accept.
    if caller_id == friendship.requested_by_id:
        raise ForbiddenError("Requester cannot accept their own friend request")

    if friendship.status == FriendshipStatus.accepted:
        raise ConflictError("Friendship already accepted")

    friendship.status = FriendshipStatus.accepted
    db.commit()
    db.refresh(friendship)
    return friendship


def list_friendships(db: Session, *, caller_id: int) -> list[Friendship]:
    stmt = (
        select(Friendship)
        .where(
            or_(
                Friendship.user_a_id == caller_id,
                Friendship.user_b_id == caller_id,
            )
        )
        .order_by(Friendship.id.desc())
    )
    return list(db.scalars(stmt).all())


def require_accepted_friendship(
    db: Session, *, user_id_1: int, user_id_2: int
) -> Friendship:
    user_a_id, user_b_id = ordered_pair(user_id_1, user_id_2)
    friendship = db.scalar(
        select(Friendship).where(
            Friendship.user_a_id == user_a_id,
            Friendship.user_b_id == user_b_id,
            Friendship.status == FriendshipStatus.accepted,
        )
    )
    if friendship is None:
        raise ValidationError("Users must be accepted friends")
    return friendship
