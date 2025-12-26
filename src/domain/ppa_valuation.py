from dataclasses import dataclass


@dataclass
class PPAResult:
    """
    Container for PPA pricing outputs.
    Keeps commercial results explicit and easy to interpret.
    """
    fair_price: float
    # Suggested fixed PPA price (€/MWh)

    capture_rate: float
    # Share of baseload price effectively captured by the technology (%)

    cannibalization_impact: float
    # Value loss vs a flat baseload profile (€/MWh)


def price_renewable_ppa(technology: str, baseload_price: float) -> PPAResult:
    """
    Estimates a fair fixed price for a Pay-As-Produced renewable PPA.

    Core idea:
    Renewable production is correlated with market prices.
    High production often coincides with lower spot prices,
    leading to structural value erosion (cannibalization).
    """

    # Capture rate assumptions based on typical Belgian / EU market estimates.
    # These values reflect production–price correlation by technology.
    capture_map = {
        "SOLAR": 0.88,
        # Solar produces mainly at midday, when prices are often depressed

        "ONSHORE_WIND": 0.92,
        # More spread production profile, but still correlated with price drops

        "OFFSHORE_WIND": 0.96,
        # High load factor and smoother profile, closer to baseload
    }

    # Retrieve capture rate, fall back to a conservative default if unknown
    capture_rate = capture_map.get(technology.upper(), 0.90)

    # Risk buffer to account for imbalance costs and operational uncertainty
    risk_buffer = 1.5  # €/MWh

    # Fair PPA price:
    # Baseload price adjusted by capture rate and risk buffer
    fair_price = (baseload_price * capture_rate) - risk_buffer

    # Cannibalization impact:
    # Value loss compared to a flat baseload generation profile
    cannibalization = baseload_price * (1.0 - capture_rate)

    return PPAResult(
        fair_price=round(fair_price, 2),
        capture_rate=round(capture_rate * 100, 1),
        cannibalization_impact=round(cannibalization, 2),
    )

