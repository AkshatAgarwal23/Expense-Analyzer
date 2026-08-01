from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Category


def list_categories(db: Session, *, caller_id: int) -> list[Category]:
    """Global defaults plus categories owned by the caller."""
    stmt = (
        select(Category)
        .where(or_(Category.owner_id.is_(None), Category.owner_id == caller_id))
        .order_by(Category.id)
    )
    return list(db.scalars(stmt).all())
