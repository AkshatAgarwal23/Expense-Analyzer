"""Pure balance netting helpers.

Positive net_paise means the other user owes the caller.
Negative means the caller owes the other user.
"""


def apply_share_delta(
    nets: dict[int, int],
    *,
    caller_id: int,
    payer_id: int,
    share_user_id: int,
    owed_paise: int,
) -> None:
    """Update nets for one expense share involving the caller."""
    if share_user_id == caller_id:
        if payer_id != caller_id:
            # Caller owes their share to the payer.
            nets[payer_id] = nets.get(payer_id, 0) - owed_paise
    elif payer_id == caller_id:
        # Other user owes their share to the caller (who paid).
        nets[share_user_id] = nets.get(share_user_id, 0) + owed_paise


def apply_settlement_delta(
    nets: dict[int, int],
    *,
    caller_id: int,
    from_user_id: int,
    to_user_id: int,
    amount_paise: int,
) -> None:
    """A settlement from A→B means A paid B, reducing what A owed B.

    From caller's view: if they received money, others owe them less (or they
    are owed less). If they paid, they owe less.
    """
    if from_user_id == caller_id:
        # Caller paid to_user → caller owes them less → net increases toward zero/positive
        nets[to_user_id] = nets.get(to_user_id, 0) + amount_paise
    elif to_user_id == caller_id:
        # from_user paid caller → they owe caller less → net decreases
        nets[from_user_id] = nets.get(from_user_id, 0) - amount_paise
