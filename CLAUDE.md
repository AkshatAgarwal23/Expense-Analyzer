# CLAUDE.md

Project context for AI assistants working in this repository.

---

## What this project is

A voice-first expense tracker with split/settle-up between users.

A user speaks a spend in any language ("400 ka dinner, Rahul ke saath split"). The app
transcribes it, extracts a structured draft, shows a confirmation screen, and — once
confirmed — writes it to a ledger that tracks both personal category spending and
who-owes-whom balances between friends.

This is a portfolio project. The author is a beginner developer building it to learn and
to discuss in technical interviews. **Explain design reasoning alongside code.** Do not
hand over working code without saying why it is shaped that way. When there is a
trade-off, name both sides and then recommend one.

---

## Hard constraints

- **No paid AI APIs.** Everything runs locally or on a free tier. This is non-negotiable
  and drives the speech and LLM choices below.
- **No money as floating point.** Ever. See "Money rules".
- **Backend before frontend.** Phases 1–4 are API-only, testable with curl.

---

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| API | FastAPI |
| Validation | Pydantic v2 |
| ORM | SQLAlchemy 2.0 (typed `Mapped[]` style) |
| Migrations | Alembic |
| Database | PostgreSQL |
| Tests | pytest |
| Speech-to-text | `faster-whisper`, running locally, in-process |
| Extraction LLM | Ollama, small local model, strict JSON output |
| Frontend (later) | React + Vite + TypeScript, mobile-first PWA |
| Auth (later) | JWT + bcrypt |

---

## Money rules

These are absolute. A violation is a bug even if tests pass.

- All amounts are stored as **integer paise** in `Integer` columns. `40000` means ₹400.00.
- Never `Float`, never `Decimal`, never rupees in the backend.
- Conversion to rupees happens **only** in the frontend display layer.
- Any variable holding a monetary value is suffixed `_paise`.

---

## Core invariants

Break any of these and balances silently corrupt.

1. **Shares sum exactly.** For every expense, `sum(share.owed_paise) == expense.amount_paise`.
   Assert this in the service layer before the transaction opens.
2. **Splits use the largest-remainder method.** ₹100 across 3 people is 3334 + 3333 + 3333,
   not `round(10000/3) * 3`. The first `remainder` participants each absorb one extra paisa.
3. **An expense and its shares are written in a single transaction.** A half-written
   expense corrupts every balance query from then on.
4. **There is no balances table.** Balances are always derived from `expense_shares` and
   `settlements`. If they get slow, add an index or a cache — never a stored mutable column.
5. **Friendships are canonically ordered.** `user_a_id < user_b_id`, enforced by a
   `CheckConstraint` plus a `UniqueConstraint` on the pair. Always go through the
   `ordered_pair()` helper; never order by hand at a call site.
6. **Settlements are append-only.** To correct one, record a reversing settlement. Never
   update or delete.

---

## Data model

Six tables:

- `users` — id, email, display_name. (No `password_hash` until auth lands.)
- `friendships` — ordered pair + status (`pending` / `accepted`)
- `categories` — id, name, owner_id (users can add their own on top of seeded defaults)
- `expenses` — amount_paise, payer_id, category_id, description, spent_on, source
- `expense_shares` — expense_id, user_id, owed_paise. One row per participant.
- `settlements` — from_user_id, to_user_id, amount_paise, settled_on

Key modelling decisions:

- **Personal spend and split spend are the same table.** A solo expense has exactly one
  share row. "My spending by category" sums the caller's share rows. "What I owe" sums
  share rows on expenses someone else paid for. One write path, two queries.
- **`payer_id` is separate from the share rows.** The person who paid is not necessarily a
  participant — you can front the cash for a meal you didn't eat.
- **`source`** is `manual` or `voice`. Used to measure extraction quality later.
- `expense_shares.expense_id` uses `ondelete="CASCADE"`. No orphan shares.
- `UniqueConstraint(expense_id, user_id)` — a person cannot appear twice in one split.

---

## Architecture

```
app/
  main.py            # FastAPI app, router wiring
  deps.py            # get_db, get_current_user_id
  models.py          # SQLAlchemy tables
  schemas/           # Pydantic request/response models
  routers/           # HTTP only: parse, call service, serialize
  services/          # business logic, no HTTP knowledge
  core/              # pure functions, no DB, no framework
tests/
```

**Imports flow downward only.**

- `core/` imports nothing from the app. Pure functions, unit-testable with no fixtures.
- `services/` may import `core/` and `models.py`. Must not import `fastapi`.
- `routers/` may import everything.

If a route handler contains business logic, it is in the wrong place. If a service raises
an `HTTPException`, it is in the wrong place — raise a domain error and let the router map it.

**Do not add a repository layer.** At this size it adds a file per table and buys nothing.
Services talk to the SQLAlchemy session directly.

**Always return through an explicit Pydantic response model.** Never serialize a SQLAlchemy
object directly — the API surface should be declared, not incidental.

### Request path for `POST /expenses`

1. Router: Pydantic validates the body → `ExpenseCreate`
2. Router: `Depends(get_current_user_id)` resolves the caller
3. Service: calls `core.splitting.split_equally(...)`
4. Service: asserts `sum(shares) == amount_paise`
5. Service: single transaction writes `Expense` + all `ExpenseShare` rows
6. Router: serializes via `ExpenseRead`

---

## Auth is deferred, not absent

Signup is not built yet. Users are created by a seed script. Identity is resolved by a
single dependency in `deps.py` that reads an `X-User-Id` header.

**Every route must resolve identity through `get_current_user_id`.** Nothing else in the
codebase may read the header. When JWT lands, that function's body changes and nothing else
does. Do not scatter header access across handlers.

---

## Build order

Do not skip ahead. Voice is the last layer, not the first — it produces the same payload a
typed form produces, so the ledger must be correct and tested before any audio is involved.

1. Schema, migration, seed script
2. `core/splitting.py` + its unit tests
3. `POST /expenses`, `GET /expenses` (manual entry, equal splits)
4. Friendships, `GET /balances`, `POST /settlements`
5. Exact and percentage split modes
6. Audio capture → `faster-whisper` → transcript endpoint
7. Transcript → LLM → strict-JSON draft → confirmation screen → existing expense service
8. Frontend, PWA, spend charts

Phase 7 must reuse `expense_service.create_expense()` unchanged. A new router and schema
only. If the voice path needs to modify the service, the layering is wrong.

---

## Extraction layer (phases 6–7)

- Run a **deterministic regex pre-pass** for amounts and known keywords before invoking the
  LLM. Rules first, AI fallback.
- The LLM must return JSON validated by a Pydantic model. Reject and retry on parse failure;
  never write unvalidated model output to the database.
- **A confirmation screen is mandatory.** The model will mishear amounts, especially in
  code-mixed Hinglish. Nothing reaches the ledger without an explicit user confirm. This is
  a designed human-in-the-loop step, not a temporary workaround.

---

## Testing

- `core/` functions get plain unit tests, no database. Cover ₹100/3, ₹0.01/2, ₹1/7.
- Service tests use a transactional fixture rolled back after each test.
- Every bug fix gets a regression test first.

---

## Conventions

- Type hints everywhere. `Mapped[]` style for SQLAlchemy models.
- Meaningful commits, pushed incrementally — not one dump at the end.
- Migrations are generated with `alembic revision --autogenerate` and **reviewed by hand**
  before applying. Autogenerate misses constraint changes.
- No secrets in the repo. `.env` is gitignored; `.env.example` is committed.