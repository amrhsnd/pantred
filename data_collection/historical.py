import pandas as pd
import yfinance as yf


class YahooFinanceClient:
    """Small adapter around yfinance for historical OHLCV data."""

    def get_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        start: str | None = None,
        end: str | None = None,
        period: str | None = None,
    ) -> pd.DataFrame:
        """
        Fetches historical data from Yahoo Finance.

        Timeframe choices include '1d', '1wk', '1mo', '1m', '5m', '15m',
        '1h', etc. Pass either start/end dates or a yfinance period such as
        '1mo', '6mo', '1y', '5y', or 'max'.
        """
        if period and (start or end):
            raise ValueError("Use either period or start/end dates, not both.")
        if not period and not start:
            raise ValueError("Provide either a period or a start date.")

        normalized_symbol = symbol.upper().strip()
        print(f"Fetching {normalized_symbol} {timeframe} data from Yahoo Finance...")

        ticker = yf.Ticker(symbol)
        history_kwargs = {"interval": timeframe, "auto_adjust": False}

        if period:
            history_kwargs["period"] = period
        else:
            history_kwargs["start"] = start
            history_kwargs["end"] = end

        df = ticker.history(**history_kwargs)

        if df.empty:
            print(f"Warning: No data returned for {normalized_symbol}")
            return pd.DataFrame()

        df = df.reset_index()
        df.columns = [
            str(col).lower().replace(" ", "_").replace("-", "_") for col in df.columns
        ]
        df.insert(0, "symbol", normalized_symbol)
        df.insert(1, "timeframe", timeframe)

        return df
