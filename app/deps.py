from fastapi import Header, HTTPException, status


def get_current_user_id(x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> int:
    """Resolve the caller from the X-User-Id header.

    Auth is deferred: seeded users + this header stand in for JWT.
    When JWT lands, only this function's body changes.
    """
    if x_user_id is None or x_user_id.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Id header",
        )
    try:
        user_id = int(x_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id must be an integer",
        ) from exc
    if user_id < 1:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id must be a positive integer",
        )
    return user_id
