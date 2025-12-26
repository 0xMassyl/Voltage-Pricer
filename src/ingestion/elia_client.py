import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional


class EliaDataConnector:
    """
    Connector to the ELIA Open Data API (v2.1).

    Objective:
    - Retrieve recent Belgian grid load and spot price data
    - Be robust to API instability, schema changes, and missing fields
    - Fall back to synthetic data when real data is unavailable
    """

    BASE_URL = "https://opendata.elia.be/api/explore/v2.1/catalog/datasets"

    # ------------------------------------------------------------------
    # Fallback generators
    # ------------------------------------------------------------------
    def _generate_fallback_load(self, days: int) -> pd.Series:
        """
        Generates a synthetic load curve when the API is unreachable
        or returns unusable data.
        """
        print("   [Elia] Fallback activated: generating synthetic load.")

        dates = pd.date_range(
            end=datetime.now(),
            periods=24 * days,
            freq="h",
            tz="Europe/Brussels",
        )

        # Stylized national load profile
        hour = dates.hour
        profile = (
            8500
            + 2000 * np.sin((hour - 6) * np.pi / 12)
            + np.random.normal(0, 150, len(dates))
        )

        return pd.Series(profile, index=dates, name="Estimated Load (MW)")

    def _generate_fallback_prices(self, days: int) -> pd.Series:
        """
        Generates synthetic spot prices when the API fails.
        """
        print("   [Elia] Fallback activated: generating synthetic prices.")

        dates = pd.date_range(
            end=datetime.now(),
            periods=24 * days,
            freq="h",
            tz="Europe/Brussels",
        )

        # Stylized intraday price pattern
        hour = dates.hour
        profile = (
            90
            + 30 * np.sin((hour - 7) * np.pi / 12)
            + np.random.normal(0, 10, len(dates))
        )

        return pd.Series(profile, index=dates, name="Estimated Price (€/MWh)")

    # ------------------------------------------------------------------
    # Generic API access
    # ------------------------------------------------------------------
    def _fetch_from_api(
        self, dataset_id: str, days: int, date_col: str = "datetime"
    ) -> pd.DataFrame:
        """
        Generic helper to query ELIA Open Data API (JSON export).

        Strategy:
        - Do not filter aggressively at query level
        - Sort by date and post-process locally for robustness
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        url = f"{self.BASE_URL}/{dataset_id}/exports/json"

        params = {
            "order_by": f"{date_col} DESC",
            "limit": 10000,  # Hard safety limit
            "timezone": "Europe/Brussels",
        }

        try:
                # Send an HTTP GET request to the ELIA Open Data API
                # - url: dataset endpoint
                # - params: query parameters (ordering, limit, timezone)
                # - timeout: prevents hanging indefinitely if the API is unresponsive
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()

            
            data = response.json()
            # If the API returns no data, return an empty DataFrame
            if not data:
                return pd.DataFrame()
            
            # Convert the JSON payload into a pandas DataFrame
            df = pd.DataFrame(data)

            # Timezone normalization and indexing
            if date_col in df.columns:
                
                # Convert the datetime column to pandas datetime format
                # - utc=True ensures timestamps are interpreted as UTC
                # - tz_convert converts them to the Europe/Brussels timezone
                df[date_col] = (
                    pd.to_datetime(df[date_col], utc=True)
                    .dt.tz_convert("Europe/Brussels")
                )
                #Set the datetime column as index and sort chronologically to ensure consistent time-series operations
                df = df.set_index(date_col).sort_index()

            return df

        except Exception as e:
            # Any failure is handled upstream via fallback logic
            print(f"   API error ({dataset_id}): {e}")
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Public API: Load
    # ------------------------------------------------------------------
    
    
    def fetch_real_load_curve(self, days: int = 14) -> pd.Series:
        """
        Retrieves Belgian grid load from dataset 'ods003'.

        The method is defensive:
        column names may change across API versions,
        so multiple candidates are tested.
        """
        print(f"[Elia] Downloading load data (ods003, last {days} days)...")


         # Fetch raw data from the ELIA API
        df = self._fetch_from_api("ods003", days, date_col="datetime")
        
        
        
        # ------------------------------------------------------------------
        ## Flexible column detection (API schema is not stable)
        # ------------------------------------------------------------------
        # The column name containing the load values may vary depending on the API version or dataset update
        target_col: Optional[str] = None
        for col in ["eliagridload", "measured", "eliagridload", "load"]:
            if col in df.columns:
                target_col = col
                break

        if df.empty or target_col is None:
            cols_found = df.columns.tolist() if not df.empty else "None"
            print(
                f"   Load column not found. Columns received: {cols_found}"
            )
            return self._generate_fallback_load(days)

        # Resample the load values to an hourly frequency,
        # compute the mean when multiple records exist,
        # interpolate missing values, and backfill remaining gaps
        hourly_load = (
            df[target_col]
            .resample("h")
            .mean()
            .interpolate()
            .bfill()
        )
        # Return a clean, continuous hourly load time series
        return hourly_load

    # ------------------------------------------------------------------
    # Public API: Spot prices
    # ------------------------------------------------------------------
    def fetch_real_spot_prices(self, days: int = 30) -> pd.Series:
        """
        Retrieves Belgian day-ahead spot prices from dataset 'ods047'.
        """
        print(f"[Elia] Downloading spot prices (ods047, last {days} days)...")

       
         # Fetch raw spot price data from the ELIA API
        df = self._fetch_from_api("ods047", days, date_col="datetime")

        # ------------------------------------------------------------------
        # Robust price column detection
        # ------------------------------------------------------------------
        
        # Normalize column names for robust matching
        df.columns = [c.lower() for c in df.columns]

        price_col: Optional[str] = None
        candidates = ["dayaheadprice", "price", "euro", "val"]

        for col in df.columns:
            if any(candidate in col for candidate in candidates):
                price_col = col
                break
  # If no valid data or price column is found, fall back to synthetic prices
        if df.empty or price_col is None:
            cols_found = df.columns.tolist() if not df.empty else "None"
            print(
                f"   Price column not found. Columns received: {cols_found}"
            )
            return self._generate_fallback_prices(days)

    # ------------------------------------------------------------------
    # Hourly time-series normalization
    # ------------------------------------------------------------------
    # Resample prices to an hourly frequency,
    # average multiple records per hour,
    # interpolate missing values, and backfill remaining gaps
    
        hourly_price = (
            df[price_col]
            .resample("h")
            .mean()
            .interpolate()
            .bfill()
        )

        return hourly_price
