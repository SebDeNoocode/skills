from decimal import Decimal

import pytest

from scripts.validate_fr import calculate_penalty, check_siren, check_vat


def test_check_siren_accepts_valid_number() -> None:
    result = check_siren("819489626")
    assert result.valid is True
    assert result.kind == "SIREN"


def test_check_siren_rejects_invalid_checksum() -> None:
    result = check_siren("819489627")
    assert result.valid is False
    assert "checksum" in result.message


@pytest.mark.parametrize("rate", ["20%", "10%", "5.5%", "2.1%", "0%"])
def test_check_vat_accepts_legal_percentage(rate: str) -> None:
    result = check_vat(rate)
    assert result.valid is True


@pytest.mark.parametrize("rate", ["0.20", "0.10", "0.055", "0.021", "0"])
def test_check_vat_accepts_legal_decimal(rate: str) -> None:
    result = check_vat(rate)
    assert result.valid is True


def test_check_vat_message_uses_plain_decimal_notation() -> None:
    result = check_vat("20%")
    assert "E" not in result.message
    assert "20%" in result.message


def test_check_vat_rejects_illegal_percentage() -> None:
    result = check_vat("15%")
    assert result.valid is False


@pytest.mark.parametrize("rate", ["NaN", "Infinity", "-20%"])
def test_check_vat_rejects_non_finite_or_negative(rate: str) -> None:
    result = check_vat(rate)
    assert result.valid is False


def test_calculate_penalty_uses_explicit_contract_rate() -> None:
    result = calculate_penalty(Decimal("1200.00"), 20, Decimal("12.15"))
    assert result.interest == Decimal("7.99")
    assert result.fixed_indemnity == Decimal("40.00")
    assert result.total == Decimal("47.99")


def test_calculate_penalty_rejects_negative_days() -> None:
    with pytest.raises(ValueError, match="days late"):
        _ = calculate_penalty(Decimal("1200.00"), -5, Decimal("12.15"))


def test_calculate_penalty_rejects_non_positive_amount() -> None:
    with pytest.raises(ValueError, match="amount must be positive"):
        _ = calculate_penalty(Decimal("0"), 20, Decimal("12.15"))
