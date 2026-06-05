from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from data_collection.heikin_ashi import add_heikin_ashi_columns
from data_collection.historical import YahooFinanceClient


@dataclass(frozen=True)
class CollectionRequest:
    symbols: list[str]
    timeframes: list[str]
    start: str | None = None
    end: str | None = None
    period: str | None = None
    output_dir: Path = Path("data/raw")
    include_heikin_ashi: bool = False


@dataclass(frozen=True)
class CollectionResult:
    symbol: str
    timeframe: str
    rows: int
    output_path: Path | None


class MarketDataCollector:
    """Collects historical market bars and writes them to local CSV files."""

    def __init__(self, client: YahooFinanceClient | None = None) -> None:
        self.client = client or YahooFinanceClient()

    def collect(self, request: CollectionRequest) -> list[CollectionResult]:
        self._validate_request(request)
        request.output_dir.mkdir(parents=True, exist_ok=True)

        results: list[CollectionResult] = []
        for symbol in self._clean_values(request.symbols):
            for timeframe in self._clean_values(request.timeframes):
                df = self.client.get_historical_bars(
                    symbol=symbol,
                    timeframe=timeframe,
                    start=request.start,
                    end=request.end,
                    period=request.period,
                )

                if request.include_heikin_ashi and not df.empty:
                    df = add_heikin_ashi_columns(df)

                output_path = None
                if not df.empty:
                    output_path = self._write_csv(
                        df=df,
                        output_dir=request.output_dir,
                        symbol=symbol,
                        timeframe=timeframe,
                    )

                results.append(
                    CollectionResult(
                        symbol=symbol.upper(),
                        timeframe=timeframe,
                        rows=len(df),
                        output_path=output_path,
                    )
                )

        self._write_manifest(request, results)
        return results

    def _write_csv(
        self,
        df: pd.DataFrame,
        output_dir: Path,
        symbol: str,
        timeframe: str,
    ) -> Path:
        symbol_dir = output_dir / self._safe_name(symbol.upper())
        symbol_dir.mkdir(parents=True, exist_ok=True)

        output_path = symbol_dir / f"{self._safe_name(timeframe)}.csv"
        df.to_csv(output_path, index=False)
        return output_path

    def _write_manifest(
        self,
        request: CollectionRequest,
        results: list[CollectionResult],
    ) -> None:
        manifest = {
            "generated_at": datetime.now(UTC).isoformat(),
            "request": {
                **asdict(request),
                "output_dir": str(request.output_dir),
            },
            "results": [
                {
                    **asdict(result),
                    "output_path": str(result.output_path) if result.output_path else None,
                }
                for result in results
            ],
        }

        manifest_path = request.output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _validate_request(self, request: CollectionRequest) -> None:
        if request.period and (request.start or request.end):
            raise ValueError("Use either period or start/end dates, not both.")
        if not request.period and not request.start:
            raise ValueError("Provide either --period or --start.")
        if not request.symbols:
            raise ValueError("Provide at least one symbol.")
        if not request.timeframes:
            raise ValueError("Provide at least one timeframe.")

    def _clean_values(self, values: Iterable[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if not cleaned:
            raise ValueError("Values cannot be empty.")
        return cleaned

    def _safe_name(self, value: str) -> str:
        return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value)
