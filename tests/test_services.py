from collections.abc import Generator
from datetime import date

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import Category, FriendshipStatus, User
from app.schemas.expenses import ExpenseCreate, SplitMode
from app.schemas.settlements import SettlementCreate
from app.services import (
    balance_service,
    expense_service,
    friendship_service,
    settlement_service,
)
from app.services.errors import ConflictError, ForbiddenError, ValidationError


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    """In-memory SQLite for service tests; schema created and dropped per test."""
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def users(db: Session) -> tuple[User, User, User]:
    a = User(email="a@example.com", display_name="A")
    b = User(email="b@example.com", display_name="B")
    c = User(email="c@example.com", display_name="C")
    db.add_all([a, b, c])
    db.flush()
    food = Category(name="Food", owner_id=None)
    db.add(food)
    db.commit()
    db.refresh(a)
    db.refresh(b)
    db.refresh(c)
    return a, b, c


@pytest.fixture()
def category_id(db: Session, users: tuple[User, User, User]) -> int:
    cat = db.scalar(select(Category).where(Category.name == "Food"))
    assert cat is not None
    return cat.id


class TestExpenseService:
    def test_equal_split_sums(
        self, db: Session, users: tuple[User, User, User], category_id: int
    ) -> None:
        a, b, c = users
        expense = expense_service.create_expense(
            db,
            caller_id=a.id,
            data=ExpenseCreate(
                amount_paise=10000,
                category_id=category_id,
                description="Dinner",
                spent_on=date(2026, 8, 1),
                participant_ids=[a.id, b.id, c.id],
                split_mode=SplitMode.equal,
            ),
        )
        assert expense.amount_paise == 10000
        assert sum(s.owed_paise for s in expense.shares) == 10000
        assert sorted(s.owed_paise for s in expense.shares) == [3333, 3333, 3334]

    def test_exact_split(
        self, db: Session, users: tuple[User, User, User], category_id: int
    ) -> None:
        a, b, _ = users
        expense = expense_service.create_expense(
            db,
            caller_id=a.id,
            data=ExpenseCreate(
                amount_paise=10000,
                category_id=category_id,
                description="Taxi",
                spent_on=date(2026, 8, 1),
                split_mode=SplitMode.exact,
                shares={a.id: 7000, b.id: 3000},
            ),
        )
        by_user = {s.user_id: s.owed_paise for s in expense.shares}
        assert by_user == {a.id: 7000, b.id: 3000}

    def test_exact_mismatch_rejected(
        self, db: Session, users: tuple[User, User, User], category_id: int
    ) -> None:
        a, b, _ = users
        with pytest.raises(ValidationError):
            expense_service.create_expense(
                db,
                caller_id=a.id,
                data=ExpenseCreate(
                    amount_paise=10000,
                    category_id=category_id,
                    description="Bad",
                    spent_on=date(2026, 8, 1),
                    split_mode=SplitMode.exact,
                    shares={a.id: 5000, b.id: 4000},
                ),
            )

    def test_percentage_split(
        self, db: Session, users: tuple[User, User, User], category_id: int
    ) -> None:
        a, b, _ = users
        expense = expense_service.create_expense(
            db,
            caller_id=a.id,
            data=ExpenseCreate(
                amount_paise=101,
                category_id=category_id,
                description="Coffee",
                spent_on=date(2026, 8, 1),
                split_mode=SplitMode.percentage,
                shares={a.id: 50, b.id: 50},
            ),
        )
        assert sum(s.owed_paise for s in expense.shares) == 101


class TestFriendshipService:
    def test_request_and_accept(self, db: Session, users: tuple[User, User, User]) -> None:
        a, b, _ = users
        friendship = friendship_service.create_friendship(
            db, caller_id=a.id, other_user_id=b.id
        )
        assert friendship.status == FriendshipStatus.pending
        assert friendship.user_a_id < friendship.user_b_id

        with pytest.raises(ForbiddenError):
            friendship_service.accept_friendship(
                db, caller_id=a.id, friendship_id=friendship.id
            )

        accepted = friendship_service.accept_friendship(
            db, caller_id=b.id, friendship_id=friendship.id
        )
        assert accepted.status == FriendshipStatus.accepted

    def test_duplicate_rejected(self, db: Session, users: tuple[User, User, User]) -> None:
        a, b, _ = users
        friendship_service.create_friendship(db, caller_id=a.id, other_user_id=b.id)
        with pytest.raises(ConflictError):
            friendship_service.create_friendship(db, caller_id=b.id, other_user_id=a.id)


class TestBalanceAndSettlement:
    def test_balance_after_expense_and_settle(
        self, db: Session, users: tuple[User, User, User], category_id: int
    ) -> None:
        a, b, _ = users
        friendship = friendship_service.create_friendship(
            db, caller_id=a.id, other_user_id=b.id
        )
        friendship_service.accept_friendship(
            db, caller_id=b.id, friendship_id=friendship.id
        )

        expense_service.create_expense(
            db,
            caller_id=a.id,
            data=ExpenseCreate(
                amount_paise=10000,
                category_id=category_id,
                description="Dinner",
                spent_on=date(2026, 8, 1),
                participant_ids=[a.id, b.id],
                split_mode=SplitMode.equal,
            ),
        )

        balances_a = {
            row.user_id: row.net_paise
            for row in balance_service.get_balances(db, caller_id=a.id)
        }
        assert balances_a[b.id] == 5000

        balances_b = {
            row.user_id: row.net_paise
            for row in balance_service.get_balances(db, caller_id=b.id)
        }
        assert balances_b[a.id] == -5000

        settlement_service.create_settlement(
            db,
            caller_id=b.id,
            data=SettlementCreate(
                to_user_id=a.id, amount_paise=5000, settled_on=date(2026, 8, 2)
            ),
        )

        balances_a_after = {
            row.user_id: row.net_paise
            for row in balance_service.get_balances(db, caller_id=a.id)
        }
        assert balances_a_after[b.id] == 0
