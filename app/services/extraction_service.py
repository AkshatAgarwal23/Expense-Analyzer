"""Transcript → ExpenseDraft via regex pre-pass + local Ollama.

Never writes to the ledger — confirm calls expense_service.create_expense().
"""

from __future__ import annotations

import json
import re
from datetime import date

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.extraction import PrepassResult, extract_prepass, guess_category_name, rupees_to_paise
from app.models import Category, Friendship, FriendshipStatus, User
from app.schemas.expenses import SplitMode
from app.schemas.voice import ExpenseDraft, ExtractResponse, LlmExpensePayload, PrepassRead
from app.services.errors import DomainError, ValidationError


class ExtractionError(DomainError):
    pass


def _friend_name_map(db: Session, caller_id: int) -> dict[str, int]:
    """Accepted friends: lowercase display_name → user_id."""
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
    names: dict[str, int] = {}
    for fid in friend_ids:
        user = db.get(User, fid)
        if user is not None:
            names[user.display_name.lower()] = user.id
    return names


def _category_name_map(db: Session, caller_id: int) -> dict[str, int]:
    cats = list(
        db.scalars(
            select(Category).where(
                or_(Category.owner_id.is_(None), Category.owner_id == caller_id)
            )
        ).all()
    )
    return {c.name.lower(): c.id for c in cats}


def _default_category_id(categories: dict[str, int]) -> int:
    if "other" in categories:
        return categories["other"]
    if categories:
        return next(iter(categories.values()))
    raise ExtractionError("No categories available — run the seed script")


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text, re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return text


def _call_ollama(prompt: str) -> str:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "format": "json",
        "keep_alive": "10m",
        "options": {
            "temperature": 0,
            "num_predict": 256,
        },
        "messages": [
            {
                "role": "system",
                "content": (
                    "Extract one expense from a short Hinglish transcript. "
                    "Reply with one JSON object only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise ExtractionError(
            f"Ollama request failed ({settings.ollama_base_url}): {exc}"
        ) from exc

    message = data.get("message") or {}
    content = message.get("content")
    if not content:
        raise ExtractionError("Ollama returned empty content")
    return str(content)


def _build_prompt(
    transcript: str,
    prepass: PrepassResult,
    friend_names: list[str],
    category_names: list[str],
) -> str:
    return f"""Transcript: {transcript!r}
Hints: amount_paise={prepass.amount_paise}, split={prepass.wants_split}, category={prepass.category_name}
Friends: {friend_names}
Categories: {category_names}
JSON keys: amount_rupees, description, category_name, friend_names, split, spent_on
"""


def _rules_only_payload(prepass: PrepassResult, transcript: str) -> LlmExpensePayload:
    """Build LLM-shaped payload from regex only — no Ollama round-trip."""
    return LlmExpensePayload(
        amount_rupees=None,
        description=(prepass.description_hint or transcript).strip(),
        category_name=prepass.category_name,
        friend_names=[],
        split=prepass.wants_split,
        spent_on=None,
    )


def _parse_llm_payload(raw: str) -> LlmExpensePayload:
    cleaned = _strip_json_fence(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Invalid JSON from model: {exc}") from exc
    return LlmExpensePayload.model_validate(data)


def _resolve_draft(
    *,
    caller_id: int,
    transcript: str,
    prepass: PrepassResult,
    llm: LlmExpensePayload,
    friends: dict[str, int],
    categories: dict[str, int],
    extra_warnings: list[str] | None = None,
) -> ExpenseDraft:
    warnings = list(prepass.warnings)
    if extra_warnings:
        warnings.extend(extra_warnings)

    if prepass.amount_paise is not None:
        amount_paise = prepass.amount_paise
    elif llm.amount_rupees is not None:
        amount_paise = rupees_to_paise(llm.amount_rupees)
    else:
        amount_paise = 0
        warnings.append("Amount missing — set amount_paise before confirm")

    category_name = (
        prepass.category_name
        or guess_category_name(transcript)
        or guess_category_name(llm.description or "")
        or llm.category_name
        or "Other"
    ).lower()
    # Normalize LLM names like "food" / "Food" via lower(); map known aliases.
    aliases = {
        "foods": "food",
        "transportation": "transport",
        "travel": "transport",
        "fuel": "transport",
        "petrol": "transport",
        "grocery": "food",
        "groceries": "food",
        "movies": "entertainment",
        "fun": "entertainment",
        "house": "rent",
        "housing": "rent",
    }
    category_name = aliases.get(category_name, category_name)
    category_id = categories.get(category_name) or _default_category_id(categories)
    if category_name not in categories:
        warnings.append(f"Unknown category {category_name!r}; using fallback")

    description = (llm.description or prepass.description_hint or transcript).strip()

    # Friends: rules first. Only names that actually appear in the transcript.
    # Ollama is given the friends list as context and often invents a split partner
    # (e.g. Rahul) for solo spends like "chai kiya 50 rupay" — ignore those.
    participant_ids = [caller_id]
    lower_transcript = transcript.lower()
    for name, fid in friends.items():
        if re.search(rf"\b{re.escape(name)}\b", lower_transcript) and fid not in participant_ids:
            participant_ids.append(fid)

    # LLM friend_names only count when that name is also in the transcript
    # (helps with capitalization / slight model wording, not invention).
    for name in llm.friend_names:
        key = name.strip().lower()
        if key not in friends:
            warnings.append(f"Unknown friend name {name!r} ignored")
            continue
        if not re.search(rf"\b{re.escape(key)}\b", lower_transcript):
            warnings.append(f"Friend {name!r} not in transcript — ignored")
            continue
        fid = friends[key]
        if fid not in participant_ids:
            participant_ids.append(fid)

    # Split if cues say so, or a friend was named in the transcript.
    # Ignore bare llm.split=true with no named friends — models invent splits.
    wants_split = prepass.wants_split or len(participant_ids) > 1
    if not wants_split:
        participant_ids = [caller_id]

    spent_on = llm.spent_on or date.today()

    return ExpenseDraft(
        amount_paise=amount_paise,
        category_id=category_id,
        description=description,
        spent_on=spent_on,
        participant_ids=participant_ids,
        payer_id=caller_id,
        split_mode=SplitMode.equal,
        shares=None,
        transcript=transcript,
        warnings=warnings,
    )


def extract_expense_draft(
    db: Session, *, caller_id: int, transcript: str
) -> ExtractResponse:
    transcript = transcript.strip()
    if not transcript:
        raise ValidationError("transcript must not be empty")

    prepass = extract_prepass(transcript)
    friends = _friend_name_map(db, caller_id)
    categories = _category_name_map(db, caller_id)
    if not categories:
        raise ExtractionError("No categories available — run the seed script")

    # Release the DB connection before slow Ollama I/O so the pool is not held.
    db.close()

    extra_warnings: list[str] = []
    use_rules_only = (
        settings.extraction_skip_llm_when_amount_found
        and prepass.amount_paise is not None
    )

    if use_rules_only:
        # Rules first: skip Ollama when amount is already known — large latency win.
        llm = _rules_only_payload(prepass, transcript)
        extra_warnings.append("Draft from rules only (Ollama skipped — amount found)")
    else:
        prompt = _build_prompt(
            transcript,
            prepass,
            friend_names=sorted(n.title() for n in friends),
            category_names=sorted(c.title() for c in categories),
        )
        raw = _call_ollama(prompt)
        try:
            llm = _parse_llm_payload(raw)
        except (ExtractionError, ValueError, TypeError):
            retry_prompt = (
                prompt
                + "\n\nPrevious reply was invalid. Return ONLY a valid JSON object."
            )
            raw = _call_ollama(retry_prompt)
            try:
                llm = _parse_llm_payload(raw)
            except (ExtractionError, ValueError, TypeError) as exc:
                raise ExtractionError(
                    f"Could not parse model JSON after retry: {exc}"
                ) from exc

    draft = _resolve_draft(
        caller_id=caller_id,
        transcript=transcript,
        prepass=prepass,
        llm=llm,
        friends=friends,
        categories=categories,
        extra_warnings=extra_warnings,
    )
    return ExtractResponse(
        draft=draft,
        prepass=PrepassRead(
            amount_paise=prepass.amount_paise,
            wants_split=prepass.wants_split,
            category_name=prepass.category_name,
            description_hint=prepass.description_hint,
            matched_amount_raw=prepass.matched_amount_raw,
            warnings=prepass.warnings,
        ),
    )
