"""Premium and deductible arithmetic (plan Section 4: eligibility and premiums).

Integer minor units only. Rates are basis points; `premium = round_half_up(insured × rate_bps / 10000)`.
"""

from decimal import ROUND_HALF_UP, Decimal

BPS = Decimal(10000)


def round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def premium_minor(insured_value_minor: int, rate_bps: int) -> int:
    return round_half_up(Decimal(insured_value_minor) * Decimal(rate_bps) / BPS)


def deductible_minor(insured_value_minor: int, deductible: dict) -> int:
    basis = deductible["basis"]
    if basis == "percent_of_insured_value":
        return round_half_up(Decimal(insured_value_minor) * Decimal(deductible["bps"]) / BPS)
    if basis == "flat":
        return int(deductible["amount_minor"])
    raise ValueError(f"unknown deductible basis {basis!r}")


def price(product: dict, insured_value_minor: int) -> dict:
    return {"premium_minor": premium_minor(insured_value_minor, product["premium"]["rate_bps"]),
            "deductible_minor": deductible_minor(insured_value_minor, product["deductible"])}


def illustrative_payout(loss_minor: int, insured_value_minor: int, deductible: int) -> int:
    """`max(0, min(eligible_loss, remaining_limit) - deductible)` from the sample basic-mortality terms."""
    return max(0, min(loss_minor, insured_value_minor) - deductible)
