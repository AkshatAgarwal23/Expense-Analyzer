from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user_id
from app.schemas.friendships import FriendshipCreate, FriendshipRead
from app.services import friendship_service
from app.services.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)

router = APIRouter(prefix="/friendships", tags=["friendships"])


def _map_error(exc: DomainError) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if isinstance(exc, ForbiddenError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.message)
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)


@router.post("", response_model=FriendshipRead, status_code=status.HTTP_201_CREATED)
def create_friendship(
    body: FriendshipCreate,
    db: Session = Depends(get_db),
    caller_id: int = Depends(get_current_user_id),
) -> FriendshipRead:
    try:
        friendship = friendship_service.create_friendship(
            db, caller_id=caller_id, other_user_id=body.user_id
        )
    except DomainError as exc:
        raise _map_error(exc) from exc
    return friendship_service.to_friendship_read(db, friendship)


@router.post("/{friendship_id}/accept", response_model=FriendshipRead)
def accept_friendship(
    friendship_id: int,
    db: Session = Depends(get_db),
    caller_id: int = Depends(get_current_user_id),
) -> FriendshipRead:
    try:
        friendship = friendship_service.accept_friendship(
            db, caller_id=caller_id, friendship_id=friendship_id
        )
    except DomainError as exc:
        raise _map_error(exc) from exc
    return friendship_service.to_friendship_read(db, friendship)


@router.get("", response_model=list[FriendshipRead])
def list_friendships(
    db: Session = Depends(get_db),
    caller_id: int = Depends(get_current_user_id),
) -> list[FriendshipRead]:
    friendships = friendship_service.list_friendships(db, caller_id=caller_id)
    return friendship_service.to_friendship_reads(db, friendships)
