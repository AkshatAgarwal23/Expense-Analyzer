import pytest

from app.core.extraction import extract_prepass, rupees_to_paise


class TestRupeesToPaise:
    def test_whole_rupees(self) -> None:
        assert rupees_to_paise(400) == 40000

    def test_decimal(self) -> None:
        assert rupees_to_paise(12.5) == 1250


class TestExtractPrepass:
    def test_400_ka_dinner(self) -> None:
        result = extract_prepass("400 ka dinner, Rahul ke saath split")
        assert result.amount_paise == 40000
        assert result.wants_split is True
        assert result.category_name == "Food"
        assert result.description_hint is not None

    def test_das_hazaar_petrol(self) -> None:
        result = extract_prepass("Das hazaar ka petrol bharwaya Rahul ke saath")
        assert result.amount_paise == 1_000_000  # ₹10,000
        assert result.category_name == "Transport"
        assert result.wants_split is True

    def test_chai_solo_no_split(self) -> None:
        """Solo chai spend must not trip split cues."""
        result = extract_prepass("chai kiya, 50 rupay lagay")
        assert result.amount_paise == 5000
        assert result.wants_split is False
        assert result.category_name == "Food"

    def test_pachaas_rupay_spoken(self) -> None:
        result = extract_prepass("chai kiya pachaas rupay lagay")
        assert result.amount_paise == 5000
        assert result.wants_split is False

    def test_bare_saath_is_not_split(self) -> None:
        """Bare 'saath' (together/60) must not mark a split — need 'ke saath'."""
        result = extract_prepass("chai kiya 50 rupay mere saath")
        assert result.wants_split is False

    def test_ke_saath_is_split(self) -> None:
        result = extract_prepass("dinner 400 Rahul ke saath")
        assert result.wants_split is True
        assert result.amount_paise == 40000

    def test_swiggy_food(self) -> None:
        result = extract_prepass("800 swiggy order")
        assert result.category_name == "Food"

    def test_myntra_shopping(self) -> None:
        result = extract_prepass("2000 myntra kapde")
        assert result.category_name == "Shopping"

    def test_pvr_entertainment(self) -> None:
        result = extract_prepass("500 pvr movie")
        assert result.category_name == "Entertainment"

    def test_kiraya_rent(self) -> None:
        result = extract_prepass("15000 kiraya")
        assert result.category_name == "Rent"

    def test_rupee_symbol(self) -> None:
        result = extract_prepass("Spent ₹250 on uber")
        assert result.amount_paise == 25000
        assert result.category_name == "Transport"

    def test_rs_suffix(self) -> None:
        result = extract_prepass("1000 rs rent")
        assert result.amount_paise == 100000
        assert result.category_name == "Rent"

    def test_no_amount(self) -> None:
        result = extract_prepass("dinner with friends")
        assert result.amount_paise is None
        assert any("amount" in w.lower() for w in result.warnings)

    def test_empty(self) -> None:
        result = extract_prepass("   ")
        assert result.amount_paise is None
        assert result.warnings
