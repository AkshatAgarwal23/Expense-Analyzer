from collections.abc import Generator
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import Category, ExpenseSource, User
from app.schemas.expenses import ExpenseCreate, SplitMode
from app.services import expense_service, extraction_service, friendship_service
from app.services.extraction_service import ExtractionError


@pytest.fixture()
def db() -> Generator[Session, None, None]:
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
def seeded(db: Session) -> tuple[User, User, int]:
    akshat = User(email="akshat@example.com", display_name="Akshat")
    rahul = User(email="rahul@example.com", display_name="Rahul")
    db.add_all([akshat, rahul])
    db.flush()
    for name in ("Food", "Transport", "Other"):
        db.add(Category(name=name, owner_id=None))
    db.commit()
    db.refresh(akshat)
    db.refresh(rahul)
    friendship = friendship_service.create_friendship(
        db, caller_id=akshat.id, other_user_id=rahul.id
    )
    friendship_service.accept_friendship(
        db, caller_id=rahul.id, friendship_id=friendship.id
    )
    food = db.scalar(select(Category).where(Category.name == "Food"))
    assert food is not None
    return akshat, rahul, food.id


class TestVoiceConfirmSource:
    def test_confirm_sets_voice_source(
        self, db: Session, seeded: tuple[User, User, int]
    ) -> None:
        akshat, rahul, food_id = seeded
        expense = expense_service.create_expense(
            db,
            caller_id=akshat.id,
            data=ExpenseCreate(
                amount_paise=40000,
                category_id=food_id,
                description="Dinner",
                spent_on=date(2026, 8, 1),
                participant_ids=[akshat.id, rahul.id],
                split_mode=SplitMode.equal,
                source=ExpenseSource.voice,
            ),
        )
        assert expense.source == ExpenseSource.voice
        assert sum(s.owed_paise for s in expense.shares) == 40000


class TestExtractionService:
    def test_extract_with_mocked_ollama(
        self, db: Session, seeded: tuple[User, User, int]
    ) -> None:
        akshat, rahul, _food_id = seeded
        # No amount in transcript → must call Ollama
        llm_json = """
        {
          "amount_rupees": 400,
          "description": "dinner with Rahul",
          "category_name": "Food",
          "friend_names": ["Rahul"],
          "split": true,
          "spent_on": null
        }
        """
        with patch(
            "app.services.extraction_service._call_ollama", return_value=llm_json
        ) as mock_ollama:
            result = extraction_service.extract_expense_draft(
                db,
                caller_id=akshat.id,
                transcript="dinner with Rahul split please",
            )

        mock_ollama.assert_called()
        assert result.draft.amount_paise == 40000
        assert result.draft.source == ExpenseSource.voice
        assert set(result.draft.participant_ids) == {akshat.id, rahul.id}

    def test_rules_only_skips_ollama_when_amount_found(
        self, db: Session, seeded: tuple[User, User, int]
    ) -> None:
        akshat, rahul, food_id = seeded
        with patch(
            "app.services.extraction_service._call_ollama"
        ) as mock_ollama:
            result = extraction_service.extract_expense_draft(
                db,
                caller_id=akshat.id,
                transcript="400 ka dinner, Rahul ke saath split",
            )

        mock_ollama.assert_not_called()
        assert result.draft.amount_paise == 40000
        assert result.draft.category_id == food_id
        assert set(result.draft.participant_ids) == {akshat.id, rahul.id}
        assert any("Ollama skipped" in w for w in result.draft.warnings)

    def test_invalid_json_retries_then_fails(
        self, db: Session, seeded: tuple[User, User, int]
    ) -> None:
        akshat, _, _ = seeded
        with patch(
            "app.services.extraction_service._call_ollama",
            return_value="not json at all {{{",
        ):
            with pytest.raises(ExtractionError, match="retry"):
                extraction_service.extract_expense_draft(
                    db, caller_id=akshat.id, transcript="dinner with friends split"
                )
