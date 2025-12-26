import pandas as pd
import numpy as np
from typing import Dict, Any
from src.ingestion.elia_client import EliaDataConnector


class MarketDataManager:
    """
    Market data layer for forward price construction.

    Role:
    - Retrieve real Belgian spot prices from ELIA
    - Calibrate the forward curve level to observable market conditions
    - Produce simple, desk-usable forward references (Base / Peak / Vol)
    """

    def __init__(self):
        # Connector to ELIA Open Data
        self.elia = EliaDataConnector()

    # ------------------------------------------------------------------
    # Forward curve construction
    # ------------------------------------------------------------------
    def get_forward_prices(self) -> Dict[str, Any]:
        """
        Builds a simplified forward curve using real spot prices as anchor.

        Output:
        - CAL_BASE: baseload forward reference
        - CAL_PEAK: peakload forward reference
        - SPOT_VOLATILITY: implied short-term spot volatility
        """
        print("[Market] Retrieving reference spot prices from ELIA...")

        # 1. Retrieve recent spot prices
        # Use a short rolling window to smooth noise
        spot_series = self.elia.fetch_real_spot_prices(days=7)

        if not spot_series.empty:
            # Spot reference as simple average
            spot_ref = spot_series.mean()
            print(
                f"[Market] 7-day average spot price: {spot_ref:.2f} €/MWh"
            )
        else:
            # Defensive fallback if API fails
            print(
                "[Market] ELIA API unavailable, using default spot reference."
            )
            spot_ref = 95.50



        # 2. Forward price construction
        # Assumption: forward prices mean-revert toward a long-term equilibrium
        # Spot level influences the forward, but does not fully dictate it
        long_term_equilibrium = 85.0
        weight_spot = 0.4

        cal_base = (
            spot_ref * weight_spot
            + long_term_equilibrium * (1 - weight_spot)
        )

        # Peakload is priced as a premium over baseload
        # This reflects structural intraday scarcity
        cal_peak = cal_base * 1.15

        # 3. Spot volatility estimation
        # Simple annualized volatility proxy based on recent data
        if not spot_series.empty and spot_series.mean() > 0:
            real_vol = (
                spot_series.std() / spot_series.mean()
            ) * np.sqrt(365)

            # Cap volatility to avoid unrealistic outputs
            volatility = max(0.15, min(real_vol, 0.80))
        else:
            volatility = 0.25

        return {
            "CAL_BASE": round(cal_base, 2),
            "CAL_PEAK": round(cal_peak, 2),
            "SPOT_VOLATILITY": round(volatility, 2),
            "SOURCE": "ELIA Open Data (Real-Time)",
        }
