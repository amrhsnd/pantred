import pandas as pd


def add_heikin_ashi_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of an OHLC dataframe with Heikin Ashi candle columns."""
    required_columns = {"open", "high", "low", "close"}
    missing_columns = required_columns.difference(df.columns)

    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required OHLC columns: {missing}")

    if df.empty:
        return df.copy()

    output = df.copy()
    ha_close = (output["open"] + output["high"] + output["low"] + output["close"]) / 4
    ha_open = ha_close.copy()
    ha_open.iloc[0] = (output["open"].iloc[0] + output["close"].iloc[0]) / 2

    for row_index in range(1, len(output)):
        ha_open.iloc[row_index] = (
            ha_open.iloc[row_index - 1] + ha_close.iloc[row_index - 1]
        ) / 2

    output["ha_open"] = ha_open
    output["ha_high"] = pd.concat([output["high"], ha_open, ha_close], axis=1).max(axis=1)
    output["ha_low"] = pd.concat([output["low"], ha_open, ha_close], axis=1).min(axis=1)
    output["ha_close"] = ha_close

    return output
