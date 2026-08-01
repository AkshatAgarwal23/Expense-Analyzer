from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, Expense, ExpenseShare
from app.schemas.analytics import CategorySpendRead


def spend_by_category(db: Session, *, caller_id: int) -> list[CategorySpendRead]:
    """Personal spend = sum of the caller's expense_shares, grouped by category."""
    stmt = (
        select(
            Category.id,
            Category.name,
            func.coalesce(func.sum(ExpenseShare.owed_paise), 0),
        )
        .join(Expense, Expense.category_id == Category.id)
        .join(ExpenseShare, ExpenseShare.expense_id == Expense.id)
        .where(ExpenseShare.user_id == caller_id)
        .group_by(Category.id, Category.name)
        .order_by(func.sum(ExpenseShare.owed_paise).desc())
    )
    rows = db.execute(stmt).all()
    return [
        CategorySpendRead(
            category_id=int(cid),
            category_name=name,
            total_paise=int(total),
        )
        for cid, name, total in rows
        if int(total) > 0
    ]
