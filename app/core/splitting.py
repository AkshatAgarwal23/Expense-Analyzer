"""Money split helpers.

All amounts are integer paise. Splits always sum exactly to amount_paise
using the largest-remainder method — never float division + round.
"""


class SplitError(ValueError):
    """Raised when a split request is invalid."""


def split_equally(amount_paise: int, n: int) -> list[int]:
    """Split amount_paise across n participants with largest-remainder.

    The first `remainder` participants each get one extra paisa so
    sum(shares) == amount_paise always.
    """
    if amount_paise < 0:
        raise SplitError("amount_paise must be >= 0")
    if n < 1:
        raise SplitError("n must be >= 1")

    base, rem = divmod(amount_paise, n)
    return [base + 1 if i < rem else base for i in range(n)]


def split_exact(amount_paise: int, owed_by_user: dict[int, int]) -> list[tuple[int, int]]:
    """Validate and return exact (user_id, owed_paise) shares."""
    if amount_paise < 0:
        raise SplitError("amount_paise must be >= 0")
    if not owed_by_user:
        raise SplitError("owed_by_user must not be empty")
    for user_id, owed in owed_by_user.items():
        if owed < 0:
            raise SplitError(f"owed_paise for user {user_id} must be >= 0")
    total = sum(owed_by_user.values())
    if total != amount_paise:
        raise SplitError(
            f"exact shares sum to {total} paise, expected {amount_paise}"
        )
    return list(owed_by_user.items())


def split_percentage(
    amount_paise: int, pct_by_user: dict[int, int]
) -> list[tuple[int, int]]:
    """Convert integer percentages (must sum to 100) into paise shares.

    Uses largest-remainder so the paise shares always sum to amount_paise.
    """
    if amount_paise < 0:
        raise SplitError("amount_paise must be >= 0")
    if not pct_by_user:
        raise SplitError("pct_by_user must not be empty")
    for user_id, pct in pct_by_user.items():
        if pct < 0:
            raise SplitError(f"percentage for user {user_id} must be >= 0")
    if sum(pct_by_user.values()) != 100:
        raise SplitError(
            f"percentages must sum to 100, got {sum(pct_by_user.values())}"
        )

    # Integer largest-remainder: floor(amount * pct / 100), then give
    # leftover paise to the largest remainders (amount * pct % 100).
    users = list(pct_by_user.keys())
    floors: list[tuple[int, int]] = []
    remainders: list[tuple[int, int, int]] = []  # (remainder, -index, user_id)
    for i, uid in enumerate(users):
        product = amount_paise * pct_by_user[uid]
        floor, rem = divmod(product, 100)
        floors.append((uid, floor))
        remainders.append((rem, -i, uid))
    leftover = amount_paise - sum(owed for _, owed in floors)
    remainders.sort(reverse=True)
    shares = {uid: owed for uid, owed in floors}
    for _, _, uid in remainders[:leftover]:
        shares[uid] += 1
    return [(uid, shares[uid]) for uid in users]
