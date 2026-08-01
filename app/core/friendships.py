"""Canonical friendship pair ordering.

Friendships store (user_a_id, user_b_id) with user_a_id < user_b_id.
Always go through ordered_pair(); never sort IDs by hand at a call site.
"""


def ordered_pair(user_id_1: int, user_id_2: int) -> tuple[int, int]:
    if user_id_1 == user_id_2:
        raise ValueError("Friendship requires two distinct users")
    if user_id_1 < user_id_2:
        return (user_id_1, user_id_2)
    return (user_id_2, user_id_1)
