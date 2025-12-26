from src.ingestion.elia_client import EliaDataConnector
import pandas as pd


def test_elia_connection():
    """
    Basic integration test for the Elia Open Data connector.
    Goal: make sure the API is reachable and returns usable time series
    for both load and spot prices.
    """

    print("--- CONNECTION TEST: ELIA OPEN DATA (BELGIUM) ---")

    # Instantiate the data connector
    # This object abstracts all API logic and formatting
    client = EliaDataConnector()

    # ------------------------------------------------------------------
    # 1. Test electricity consumption (real load curve)
    # ------------------------------------------------------------------
    print("\n1. Downloading real load curve...")

    try:
        # Fetch last 3 days of load data
        # Short horizon on purpose: fast to test, enough to validate format
        load_curve = client.fetch_real_load_curve(days=3)

        # Basic sanity check on returned data
        if not load_curve.empty:
            print("SUCCESS: Load data received.")
            print(f"   -> Number of observations: {len(load_curve)}")
            print(f"   -> Average load: {load_curve.mean():.2f} MW")

            # Display a small sample to visually inspect timestamps and values
            print("\n   Data preview:")
            print(load_curve.head(3))
        else:
            # Empty DataFrame usually means API response issue or parsing failure
            print("FAILURE: No load data received (empty DataFrame).")

    except Exception as e:
        # Catch any unexpected error (network, API change, parsing issue)
        print(f"ERROR while downloading load data: {e}")

    # ------------------------------------------------------------------
    # 2. Test spot electricity prices
    # ------------------------------------------------------------------
    print("\n2. Downloading spot prices...")

    try:
        # Fetch last 3 days of spot prices
        prices = client.fetch_real_spot_prices(days=3)

        # Same validation logic as for load data
        if not prices.empty:
            print("SUCCESS: Price data received.")
            print(f"   -> Number of observations: {len(prices)}")
            print(f"   -> Average price: {prices.mean():.2f} €/MWh")

            # Quick visual check of the time series
            print("\n   Data preview:")
            print(prices.head(3))
        else:
            print("FAILURE: No price data received (empty DataFrame).")

    except Exception as e:
        print(f"ERROR while downloading price data: {e}")

    print("\n--- END OF DIAGNOSTIC ---")


if __name__ == "__main__":
    # Entry point for manual execution
    # Allows running the test without a test framework
    test_elia_connection()


