"""Read-only Hyperliquid perpetual market data. No wallet or signing keys."""

from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


INTERVALS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
    "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000,
    "4h": 14_400_000, "8h": 28_800_000, "12h": 43_200_000,
    "1d": 86_400_000, "3d": 259_200_000, "1w": 604_800_000,
    "1M": None,
}


def now_ms() -> int:
    return time.time_ns() // 1_000_000


class HyperliquidClient:
    def __init__(self, testnet: bool = False) -> None:
        self.network = "testnet" if testnet else "mainnet"
        host = "api.hyperliquid-testnet.xyz" if testnet else "api.hyperliquid.xyz"
        self.info_url = f"https://{host}/info"
        self.ws_url = f"wss://{host}/ws"
        self._last_request = 0.0

    def info(self, payload: dict) -> object:
        for attempt in range(4):
            # Pace REST backfills independently of the streaming connection.
            time.sleep(max(0, 0.3 - (time.monotonic() - self._last_request)))
            self._last_request = time.monotonic()
            request = Request(self.info_url, data=json.dumps(payload).encode(),
                              headers={"Content-Type": "application/json"})
            try:
                with urlopen(request, timeout=10) as response:
                    result = json.load(response)
                if isinstance(result, str) or (
                    isinstance(result, dict) and "error" in result
                ):
                    raise ValueError(f"Hyperliquid rejected request: {result}")
                return result
            except HTTPError as exc:
                if exc.code != 429 and exc.code < 500:
                    raise ValueError(f"Hyperliquid HTTP {exc.code}") from exc
                retry_after = exc.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else 2 ** attempt
            except (URLError, TimeoutError, ConnectionError):
                delay = 2 ** attempt
            if attempt == 3:
                raise ConnectionError("Hyperliquid unavailable after four attempts")
            time.sleep(min(delay, 60))
        raise AssertionError("unreachable")

    def markets(self, dex: str = "") -> list[dict]:
        metadata, contexts = self.info({"type": "metaAndAssetCtxs", "dex": dex})
        universe = metadata["universe"]
        if len(universe) != len(contexts):
            raise ValueError("Hyperliquid metadata/context lengths differ")
        return [
            {**asset, "context": context, "dex": dex}
            for asset, context in zip(universe, contexts)
            if not asset.get("isDelisted", False)
        ]

    def resolve_symbols(self, symbols: list[str], dex: str = "") -> list[str]:
        names = {market["name"].casefold(): market["name"] for market in self.markets(dex)}
        resolved = []
        for symbol in symbols:
            key = symbol.strip().casefold()
            if dex and ":" not in key:
                key = f"{dex.casefold()}:{key}"
            if key not in names:
                raise ValueError(f"Unknown active perpetual: {symbol}. Use the markets command.")
            if names[key] not in resolved:
                resolved.append(names[key])
        if not resolved:
            raise ValueError("At least one perpetual symbol is required")
        return resolved

    def candles(self, symbol: str, interval: str, start_ms: int, end_ms: int) -> list[dict]:
        if interval not in INTERVALS:
            raise ValueError(f"Unsupported candle interval: {interval}")
        if start_ms >= end_ms:
            raise ValueError("Start must be before end")
        result = self.info({"type": "candleSnapshot", "req": {
            "coin": symbol, "interval": interval, "startTime": start_ms,
            "endTime": end_ms - 1,
        }})
        if not isinstance(result, list):
            raise ValueError("Unexpected candle response")
        # Hyperliquid may return a candle overlapping the requested start.
        return sorted((row for row in result if start_ms <= int(row["t"]) < end_ms),
                      key=lambda row: int(row["t"]))
