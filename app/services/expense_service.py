from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.splitting import SplitError, split_equally, split_exact, split_percentage
from app.models import Category, Expense, ExpenseShare, User
from app.schemas.expenses import ExpenseCreate, SplitMode
from app.services.errors import NotFoundError, ValidationError


def _resolve_shares(
    data: ExpenseCreate,
) -> list[tuple[int, int]]:
    if data.split_mode == SplitMode.equal:
        if not data.participant_ids:
            raise ValidationError("participant_ids required for equal split")
        if len(set(data.participant_ids)) != len(data.participant_ids):
            raise ValidationError("participant_ids must be unique")
        amounts = split_equally(data.amount_paise, len(data.participant_ids))
        return list(zip(data.participant_ids, amounts, strict=True))

    if data.shares is None or not data.shares:
        raise ValidationError(f"shares required for {data.split_mode.value} split")

    try:
        if data.split_mode == SplitMode.exact:
            return split_exact(data.amount_paise, data.shares)
        if data.split_mode == SplitMode.percentage:
            return split_percentage(data.amount_paise, data.shares)
    except SplitError as exc:
        raise ValidationError(str(exc)) from exc

    raise ValidationError(f"unsupported split_mode: {data.split_mode}")


def create_expense(
    db: Session, *, caller_id: int, data: ExpenseCreate
) -> Expense:
    payer_id = data.payer_id if data.payer_id is not None else caller_id

    payer = db.get(User, payer_id)
    if payer is None:
        raise NotFoundError(f"payer {payer_id} not found")

    category = db.get(Category, data.category_id)
    if category is None:
        raise NotFoundError(f"category {data.category_id} not found")

    share_pairs = _resolve_shares(data)
    share_user_ids = [uid for uid, _ in share_pairs]
    for uid in share_user_ids:
        if db.get(User, uid) is None:
            raise NotFoundError(f"participant {uid} not found")

    total = sum(owed for _, owed in share_pairs)
    # Invariant #1: shares must sum exactly before the transaction opens.
    assert total == data.amount_paise, (
        f"share sum {total} != amount_paise {data.amount_paise}"
    )

    expense = Expense(
        amount_paise=data.amount_paise,
        payer_id=payer_id,
        category_id=data.category_id,
        description=data.description,
        spent_on=data.spent_on,
        source=data.source,
    )
    for user_id, owed_paise in share_pairs:
        expense.shares.append(
            ExpenseShare(user_id=user_id, owed_paise=owed_paise)
        )

    db.add(expense)
    db.commit()
    db.refresh(expense)
    # Reload with shares for response serialization.
    loaded = db.scalar(
        select(Expense)
        .where(Expense.id == expense.id)
        .options(selectinload(Expense.shares))
    )
    assert loaded is not None
    return loaded


def list_expenses(db: Session, *, caller_id: int) -> list[Expense]:
    """Expenses where the caller is payer or a share participant."""
    share_expense_ids = select(ExpenseShare.expense_id).where(
        ExpenseShare.user_id == caller_id
    )
    stmt = (
        select(Expense)
        .where(
            (Expense.payer_id == caller_id) | (Expense.id.in_(share_expense_ids))
        )
        .options(selectinload(Expense.shares))
        .order_by(Expense.spent_on.desc(), Expense.id.desc())
    )
    return list(db.scalars(stmt).unique().all())
