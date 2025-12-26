import pandas as pd
import numpy as np
from src.core.settings import SETTINGS
from src.ingestion.elia_client import EliaDataConnector


class LoadCurveGenerator:
    """
    Hybrid load curve generator.

    Logic:
    1. Attempt to retrieve real load data from the Elia Open Data API
       to capture realistic consumption patterns.
    2. Fall back to synthetic profile generation when real data
       is unavailable or not applicable.

    Purpose: generate realistic hourly consumption or production profiles
    suitable for pricing, risk, and sourcing analysis.
    """

    def __init__(self, year: int = 2026):
        # - year: target year for which the hourly profile is generated
        self.year = year

        # Generate a full hourly datetime index for the entire year (from Jan 1st 00:00 to Dec 31st 23:00)
        self.dates = pd.date_range(
            start=f"{year}-01-01",
            end=f"{year}-12-31 23:00",
            freq="h",
        )
        # Total number of hours in the target year
        self.n_hours = len(self.dates)

        # Connector to Elia Open Data
        self.elia = EliaDataConnector()

    # ------------------------------------------------------------------
    # Profile generation
    # ------------------------------------------------------------------
    def generate_profile(
        self, profile_type: str, annual_volume_mwh: float
    ) -> pd.Series:
        """
        Generates an hourly load or production profile.

        profile_type:
        Defines the structural shape (industry, office, solar, etc.).

        annual_volume_mwh:
        Target annual energy volume used for normalization.
        """

        # --------------------------------------------------------------
        # Attempt to use real Elia data (only for 24/7 industrial profile)
        # --------------------------------------------------------------
        if profile_type == "INDUSTRY_24_7":
            print("Attempting to retrieve real Elia load profile...")

            # Retrieve a short recent load curve to use as a representative shape
            real_curve = self.elia.fetch_real_load_curve(days=14)

            if not real_curve.empty:
                # Convert the hourly load series to a numpy array
                pattern = real_curve.to_numpy()

                # Repeat the short pattern to cover the full year
                repeats = int((self.n_hours // len(pattern)) + 1)
                full_pattern = np.tile(pattern, repeats)[: self.n_hours]

                # Normalize the repeated pattern to match the target annual volume
                total_units = full_pattern.sum()
                if total_units == 0:
                    normalized_curve = np.zeros(self.n_hours)
                else:
                    normalized_curve = (
                        full_pattern / total_units
                    ) * annual_volume_mwh

                print("Load profile generated using real Elia data.")
                return pd.Series(
                    normalized_curve,
                    index=self.dates,
                    name="Real Load (MWh)",
                )

        # --------------------------------------------------------------
        # Fallback: synthetic profile generation
        # --------------------------------------------------------------
        print("Using synthetic load generator (fallback).")
        
        # Initialize the base curve with zeros
        base_curve = np.zeros(self.n_hours)


# --------------------------------------------------------------
# CASE 1: INDUSTRIAL SITE OPERATING 24/7
# --------------------------------------------------------------
        if profile_type == "INDUSTRY_24_7":
        # Generate a base consumption signal with small random variations.
        # - mean = 1.0 → reference consumption level (relative scale)
        # - std = 0.05 → low variability, typical of industrial processes
        # - size = self.n_hours → one value per hour of the year
            base_curve = np.random.normal(1.0, 0.05, self.n_hours)
            
        # Identify weekend hours using the calendar
        # dayofweek: Monday = 0, Sunday = 6
        # SETTINGS.WEEKEND_DAYS typically contains [5, 6] (Saturday, Sunday)
            is_weekend = self.dates.dayofweek.isin(SETTINGS.WEEKEND_DAYS)
            
            
        # Reduce consumption during weekends
        # Industrial activity is assumed to be slightly lower, but not fully stopped (continuous processes)
            base_curve[is_weekend] *= 0.85
            
            
            
            
# --------------------------------------------------------------
# CASE 2: OFFICE BUILDING
# --------------------------------------------------------------
        elif profile_type == "OFFICE_BUILDING":
            # Identify working hours:
            # - between 08:00 and 18:00
            # - Monday to Friday only (dayofweek < 5)

            hour = self.dates.hour
            is_working = (
                (hour >= 8)
                & (hour <= 18)
                & (self.dates.dayofweek < 5)
            )
            # Assign higher consumption during working hours
            # Random noise reflects day-to-day operational variability
            base_curve[is_working] = np.random.normal(
                1.0, 0.1, is_working.sum()
            )
            base_curve[~is_working] = 0.1
            
            
            
            
# --------------------------------------------------------------
# CASE 3: SOLAR PRODUCTION PROFILE
# --------------------------------------------------------------
        elif profile_type == "SOLAR_PPA":
            # Identify daylight hours
            # Solar production is assumed to occur between 06:00 and 20:00
            hour = self.dates.hour
            daylight = (hour >= 6) & (hour <= 20)
            # Generate a smooth sinusoidal production profile during daylight
            # - Production starts at sunrise, peaks around midday,
            #   and returns to zero at sunset
            # - The sine function provides a simple, realistic shape
            
            
            base_curve[daylight] = np.sin(
                (hour[daylight] - 6) * np.pi / 14
            )
            # Prevent negative values (night-time or numerical artifacts)
            # Solar production cannot be negative
            base_curve = np.maximum(base_curve, 0)

        
        # Compute the total "raw" energy represented by the synthetic curve.
        # At this stage, base_curve contains only relative values
        total_units = base_curve.sum()
        
        # If the curve contains non-zero values, scale it so that the total annual energy equals the requested volume.
        if total_units > 0:
            normalized_curve = (base_curve / total_units) * annual_volume_mwh
        else:
            # Defensive fallback:
            # if the curve is entirely zero (edge case),
            # return it as-is to avoid division by zero
            normalized_curve = base_curve



        # Return the final synthetic load profile as a pandas Series
        # - indexed hourly over the full year
        # - expressed in energy units (MWh)
        return pd.Series(
            normalized_curve,
            index=self.dates,
            name="Synthetic Load",
        )
