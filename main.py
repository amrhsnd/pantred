from data_collection.historical import YahooFinanceClient

# Initialize your new Yahoo client
client = YahooFinanceClient()

# Fetch data (Note: yfinance uses '1d' instead of '1Day')
data = client.get_historical_bars(
    symbol="AAPL", 
    timeframe="1d", 
    start="2026-01-01", 
    # yfinance 'end' date is exclusive, so this fetches up to May 14th
    end="2026-05-15" 
)

# View your market data
print(data.head())