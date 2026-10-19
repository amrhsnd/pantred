"""Continuous public-market recorder with heartbeat and reconnect recovery."""

import asyncio
import json
import logging
import time
from contextlib import suppress

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from data_collection.hyperliquid import INTERVALS, HyperliquidClient, now_ms
from data_collection.market_store import MarketStore

LOG = logging.getLogger(__name__)


def backfill(client: HyperliquidClient, store: MarketStore, symbols: list[str],
             intervals: list[str], start_ms: int, end_ms: int, resume: bool = False) -> None:
    for symbol in symbols:
        for interval in intervals:
            start = start_ms
            last = store.last_candle(symbol, interval)
            if resume and last is not None:
                start = min(last, end_ms - 1)
            candles = client.candles(symbol, interval, start, end_ms)
            store.save_candles(candles)
            step = INTERVALS[interval]
            warnings = []
            if not candles:
                warnings.append("No candles returned")
            elif step:
                first_expected = ((start + step - 1) // step) * step
                if interval != "1w" and candles[0]["t"] > first_expected:
                    warnings.append("Leading history unavailable (retention or listing boundary)")
                if any(b["t"] - a["t"] != step for a, b in zip(candles, candles[1:])):
                    warnings.append("Internal candle gaps detected")
            detail = f"{symbol} {interval}: {len(candles)} candles; requested [{start}, {end_ms})"
            store.event("backfill", detail)
            LOG.info(detail)
            for warning in warnings:
                store.event("coverage_warning", f"{symbol} {interval}: {warning}")
                LOG.warning("%s %s: %s", symbol, interval, warning)
            store.db.commit()


def subscriptions(symbols: list[str], intervals: list[str]) -> list[dict]:
    return [subscription for symbol in symbols for subscription in (
        [{"type": channel, "coin": symbol} for channel in ("trades", "l2Book", "activeAssetCtx")]
        + [{"type": "candle", "coin": symbol, "interval": interval} for interval in intervals]
    )]


async def heartbeat(socket) -> None:
    while True:
        await asyncio.sleep(20)
        await socket.send(json.dumps({"method": "ping"}))


async def record(client: HyperliquidClient, store: MarketStore, symbols: list[str],
                 intervals: list[str], lookback_hours: float = 24,
                 duration: float | None = None) -> None:
    feeds = subscriptions(symbols, intervals)
    if len(feeds) > 100:
        raise ValueError("This local recorder supports at most 100 subscriptions per run")
    if duration is not None and duration <= 0:
        raise ValueError("Duration must be positive")
    if lookback_hours <= 0:
        raise ValueError("Lookback hours must be positive")
    deadline = time.monotonic() + duration if duration is not None else float("inf")
    backoff = 1
    store.event("started", f"symbols={symbols}; intervals={intervals}")
    store.db.commit()
    try:
        while time.monotonic() < deadline:
            try:
                # Synchronous backfill keeps SQLite writes in this thread. It happens
                # before connecting, so it cannot delay handling a live message.
                end = now_ms()
                backfill(client, store, symbols, intervals,
                         end - int(lookback_hours * 3_600_000), end, resume=True)
                if time.monotonic() >= deadline:
                    break
                async with connect(client.ws_url, open_timeout=10, close_timeout=3,
                                   ping_interval=20, ping_timeout=20) as socket:
                    for feed in feeds:
                        await socket.send(json.dumps({"method": "subscribe", "subscription": feed}))
                    store.event("connected", "Trade/book history during offline periods is not recoverable here")
                    store.db.commit()
                    LOG.info("Recording %s (%s). Ctrl+C stops and flushes data.", symbols, client.network)
                    ping = asyncio.create_task(heartbeat(socket))
                    last_commit = time.monotonic()
                    connected_at = time.monotonic()
                    last_data = connected_at
                    received_feeds = set()
                    try:
                        while time.monotonic() < deadline:
                            remaining = deadline - time.monotonic()
                            try:
                                raw = await asyncio.wait_for(socket.recv(), timeout=min(5, remaining))
                            except asyncio.TimeoutError:
                                if time.monotonic() - last_data > 60:
                                    raise TimeoutError("No market data for 60 seconds")
                            else:
                                message = json.loads(raw)
                                if store.save_message(message):
                                    last_data = time.monotonic()
                                    received_feeds.add(message["channel"])
                                if time.monotonic() - connected_at > 60:
                                    backoff = 1
                            if time.monotonic() - last_commit >= 1:
                                store.db.commit()
                                last_commit = time.monotonic()
                    finally:
                        ping.cancel()
                        with suppress(asyncio.CancelledError, ConnectionClosed):
                            await ping
                        store.event("session_end", f"Received channels: {sorted(received_feeds)}")
                        store.db.commit()
            except (OSError, ConnectionClosed, InvalidStatus, TimeoutError) as exc:
                store.event("disconnected", f"{type(exc).__name__}: {exc}; possible trade/book gap")
                store.db.commit()
                LOG.warning("Connection interrupted: %s; retry in %ss", exc, backoff)
                await asyncio.sleep(max(0, min(backoff, deadline - time.monotonic())))
                backoff = min(backoff * 2, 30)
    except Exception as exc:
        store.event("failed", f"{type(exc).__name__}: {exc}")
        raise
    finally:
        store.event("stopped", "Recorder stopped; observations flushed")
        store.db.commit()
