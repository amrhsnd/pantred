import pandas as pd
import yfinance as yf

class YahooFinanceClient:
    def __init__(self):
        # No API key needed for yfinance!
        pass

    def get_historical_bars(self, symbol: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
        """
        Fetches historical data from Yahoo Finance.
        timeframe choices: '1d', '1wk', '1mo', '1m', '5m', '15m', '1h' etc.
        """
        print(f"Fetching {symbol} data from Yahoo Finance...")
        
        # yf.Ticker initializes the instrument
        ticker = yf.Ticker(symbol)
        
        # Fetch the historical price data
        df = ticker.history(interval=timeframe, start=start, end=end)
        
        if df.empty:
            print(f"Warning: No data returned for {symbol}")
            return pd.DataFrame()
            
        # Clean up column names to lowercase for consistency in your project
        df.columns = [col.lower() for col in df.columns]
        
        return df