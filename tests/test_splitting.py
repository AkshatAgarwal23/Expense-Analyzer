import pytest

from app.core.friendships import ordered_pair
from app.core.splitting import SplitError, split_equally, split_exact, split_percentage


class TestSplitEqually:
    def test_rupees_100_across_3(self) -> None:
        # ₹100 = 10000 paise → 3334 + 3333 + 3333
        assert split_equally(10000, 3) == [3334, 3333, 3333]
        assert sum(split_equally(10000, 3)) == 10000

    def test_one_paisa_across_2(self) -> None:
        assert split_equally(1, 2) == [1, 0]
        assert sum(split_equally(1, 2)) == 1

    def test_rupee_across_7(self) -> None:
        shares = split_equally(100, 7)
        assert sum(shares) == 100
        assert shares == [15, 15, 14, 14, 14, 14, 14]

    def test_solo(self) -> None:
        assert split_equally(5000, 1) == [5000]

    def test_rejects_bad_n(self) -> None:
        with pytest.raises(SplitError):
            split_equally(100, 0)

    def test_rejects_negative(self) -> None:
        with pytest.raises(SplitError):
            split_equally(-1, 2)


class TestSplitExact:
    def test_exact_ok(self) -> None:
        assert split_exact(10000, {1: 6000, 2: 4000}) == [(1, 6000), (2, 4000)]

    def test_exact_mismatch(self) -> None:
        with pytest.raises(SplitError, match="sum"):
            split_exact(10000, {1: 6000, 2: 3000})


class TestSplitPercentage:
    def test_fifty_fifty_odd_paise(self) -> None:
        # 101 paise, 50/50 → largest remainder gives first the extra
        shares = split_percentage(101, {1: 50, 2: 50})
        assert sum(owed for _, owed in shares) == 101
        assert dict(shares) == {1: 51, 2: 50}

    def test_must_sum_to_100(self) -> None:
        with pytest.raises(SplitError, match="100"):
            split_percentage(10000, {1: 60, 2: 30})


class TestOrderedPair:
    def test_orders(self) -> None:
        assert ordered_pair(5, 2) == (2, 5)
        assert ordered_pair(2, 5) == (2, 5)

    def test_rejects_same(self) -> None:
        with pytest.raises(ValueError):
            ordered_pair(1, 1)
