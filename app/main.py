from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.routers import analytics, balances, categories, expenses, friendships, me, settlements, voice
from app.database import get_db
from app.models import User, Category

app = FastAPI(title="Expense Analyzer", version="0.1.0")

app.include_router(me.router)
app.include_router(expenses.router)
app.include_router(friendships.router)
app.include_router(balances.router)
app.include_router(settlements.router)
app.include_router(categories.router)
app.include_router(analytics.router)
app.include_router(voice.router)

static_dir = Path(__file__).resolve().parent.parent / "static"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# TEMPORARY — delete this endpoint after running once in production
@app.post("/seed")
def seed_db(db: Session = Depends(get_db)) -> dict:
    USERS = [
        ("akshat@example.com", "Akshat"),
        ("rahul@example.com", "Rahul"),
        ("priya@example.com", "Priya"),
    ]
    DEFAULT_CATEGORIES = ["Food", "Transport", "Rent", "Shopping", "Entertainment", "Other"]

    seeded_users = []
    for email, display_name in USERS:
        existing = db.scalar(select(User).where(User.email == email))
        if existing is None:
            user = User(email=email, display_name=display_name)
            db.add(user)
            db.flush()
            seeded_users.append({"email": email, "display_name": display_name, "id": user.id})
        else:
            seeded_users.append({"email": email, "display_name": display_name, "id": existing.id})
    db.commit()

    seeded_cats = []
    for name in DEFAULT_CATEGORIES:
        existing = db.scalar(select(Category).where(Category.name == name, Category.owner_id.is_(None)))
        if existing is None:
            cat = Category(name=name, owner_id=None)
            db.add(cat)
            db.flush()
            seeded_cats.append({"name": name, "id": cat.id})
        else:
            seeded_cats.append({"name": name, "id": existing.id})
    db.commit()

    return {"users": seeded_users, "categories": seeded_cats}


@app.get("/")
def landing() -> FileResponse:
    """Kharcha dashboard — spend overview, balances, voice CTA."""
    return FileResponse(static_dir / "kharcha-dashboard.html")


if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
