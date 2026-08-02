from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.balances import apply_settlement_delta, apply_share_delta
from app.models import Expense, Friendship, FriendshipStatus, Settlement, User
from app.schemas.balances import BalanceRead


def get_balances(db: Session, *, caller_id: int) -> list[BalanceRead]:
    """Derive net balances with each accepted friend. No balances table."""
    friendships = list(
        db.scalars(
            select(Friendship).where(
                Friendship.status == FriendshipStatus.accepted,
                or_(
                    Friendship.user_a_id == caller_id,
                    Friendship.user_b_id == caller_id,
                ),
            )
        ).all()
    )
    friend_ids = {
        f.user_b_id if f.user_a_id == caller_id else f.user_a_id for f in friendships
    }
    nets: dict[int, int] = {fid: 0 for fid in friend_ids}

    expenses = list(
        db.scalars(
            select(Expense).options(selectinload(Expense.shares))
        ).all()
    )
    for expense in expenses:
        for share in expense.shares:
            if expense.payer_id != caller_id and share.user_id != caller_id:
                continue
            other_candidates = {expense.payer_id, share.user_id} - {caller_id}
            # Only track nets against accepted friends.
            if not other_candidates:
                continue
            apply_share_delta(
                nets,
                caller_id=caller_id,
                payer_id=expense.payer_id,
                share_user_id=share.user_id,
                owed_paise=share.owed_paise,
            )

    # Drop accidental keys for non-friends introduced by share math.
    nets = {fid: nets.get(fid, 0) for fid in friend_ids}

    settlements = list(
        db.scalars(
            select(Settlement).where(
                or_(
                    Settlement.from_user_id == caller_id,
                    Settlement.to_user_id == caller_id,
                )
            )
        ).all()
    )
    for settlement in settlements:
        other_id = (
            settlement.to_user_id
            if settlement.from_user_id == caller_id
            else settlement.from_user_id
        )
        if other_id not in friend_ids:
            continue
        apply_settlement_delta(
            nets,
            caller_id=caller_id,
            from_user_id=settlement.from_user_id,
            to_user_id=settlement.to_user_id,
            amount_paise=settlement.amount_paise,
        )

    names: dict[int, str] = {}
    if friend_ids:
        for user in db.scalars(select(User).where(User.id.in_(friend_ids))).all():
            names[user.id] = user.display_name

    return [
        BalanceRead(
            user_id=uid,
            display_name=names.get(uid, f"User {uid}"),
            net_paise=nets[uid],
        )
        for uid in sorted(nets.keys())
    ]
