from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.routers import analytics, balances, categories, expenses, friendships, settlements, voice

app = FastAPI(title="Expense Analyzer", version="0.1.0")

app.include_router(expenses.router)
app.include_router(friendships.router)
app.include_router(balances.router)
app.include_router(settlements.router)
app.include_router(categories.router)
app.include_router(analytics.router)
app.include_router(voice.router)

static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
