"""Idempotent local seed: users + default categories.

Run: python -m scripts.seed
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `python scripts/seed.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Category, User

USERS = [
    ("akshat@example.com", "Akshat"),
    ("rahul@example.com", "Rahul"),
    ("priya@example.com", "Priya"),
]

DEFAULT_CATEGORIES = [
    "Food",
    "Transport",
    "Rent",
    "Shopping",
    "Entertainment",
    "Other",
]


def seed() -> None:
    db = SessionLocal()
    try:
        for email, display_name in USERS:
            existing = db.scalar(select(User).where(User.email == email))
            if existing is None:
                db.add(User(email=email, display_name=display_name))
        db.commit()

        for name in DEFAULT_CATEGORIES:
            existing = db.scalar(
                select(Category).where(
                    Category.name == name, Category.owner_id.is_(None)
                )
            )
            if existing is None:
                db.add(Category(name=name, owner_id=None))
        db.commit()

        users = list(db.scalars(select(User).order_by(User.id)).all())
        categories = list(
            db.scalars(
                select(Category)
                .where(Category.owner_id.is_(None))
                .order_by(Category.id)
            ).all()
        )

        print("Seeded users (use as X-User-Id):")
        for user in users:
            print(f"  id={user.id}  {user.display_name}  <{user.email}>")
        print("Default categories:")
        for category in categories:
            print(f"  id={category.id}  {category.name}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
