"""Kraken spot market data connector."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Optional

import websockets
from websockets.client import WebSocketClientProtocol

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class KrakenTicker:
    """Represents a single Kraken ticker update."""

    pair: str
    price: float
    best_bid: float
    best_ask: float
    event_time_ms: int


class KrakenTickerClient:
    """Connects to Kraken websocket and yields ticker updates."""

    def __init__(
        self,
        *,
        pair: str,
        base_ws_url: str = "wss://ws.kraken.com",
        reconnect_interval: float = 1.0,
        max_reconnect_interval: float = 8.0,
    ) -> None:
        self._raw_pair = pair.upper()
        self._pair = self._raw_pair
        self._endpoint = base_ws_url
        self._reconnect_interval = reconnect_interval
        self._max_reconnect_interval = max_reconnect_interval
        self._ws: Optional[WebSocketClientProtocol] = None
        self._stopping = asyncio.Event()

    @property
    def pair(self) -> str:
        return self._raw_pair

    async def stop(self) -> None:
        """Signal the client to stop streaming."""

        self._stopping.set()
        if self._ws is not None and not self._ws.closed:
            await self._ws.close(code=1000)

    async def stream(self) -> AsyncGenerator[KrakenTicker, None]:
        """Async generator that yields price updates."""

        backoff = self._reconnect_interval
        subscribe_payload = json.dumps(
            {
                "event": "subscribe",
                "pair": [self._pair],
                "subscription": {"name": "ticker"},
            }
        )
        while not self._stopping.is_set():
            try:
                LOGGER.debug("Connecting to Kraken websocket %s", self._endpoint)
                async with websockets.connect(
                    self._endpoint,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                    max_queue=None,
                ) as ws:
                    self._ws = ws
                    await ws.send(subscribe_payload)
                    backoff = self._reconnect_interval
                    async for raw in ws:
                        if self._stopping.is_set():
                            break
                        message = json.loads(raw)
                        ticker = self._parse_message(message)
                        if ticker is not None:
                            yield ticker
            except Exception as exc:  # pragma: no cover - network resilience
                LOGGER.warning("Kraken stream error: %s", exc, exc_info=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._max_reconnect_interval)
            finally:
                if self._ws is not None:
                    await self._ws.close(code=1001)
                    self._ws = None

    def _parse_message(self, message) -> Optional[KrakenTicker]:
        if isinstance(message, dict):
            # system status, heartbeat, subscription status
            return None
        if not isinstance(message, list):
            return None
        if len(message) < 4:
            return None
        if message[-2] != "ticker":
            return None
        data = message[1]
        if not isinstance(data, dict):
            return None

        best_ask = self._extract_price(data.get("a"))
        best_bid = self._extract_price(data.get("b"))
        last_trade = self._extract_price(data.get("c"))
        if last_trade is None:
            last_trade = self._extract_price(data.get("p"))

        if best_bid is None and best_ask is None and last_trade is None:
            return None

        price_components = [p for p in (best_bid, best_ask, last_trade) if p is not None]
        price = sum(price_components) / len(price_components)
        timestamp_ms = int(time.time() * 1000)
        return KrakenTicker(
            pair=self._pair,
            price=price,
            best_bid=best_bid or price,
            best_ask=best_ask or price,
            event_time_ms=timestamp_ms,
        )

    @staticmethod
    def _extract_price(field: Optional[list]) -> Optional[float]:
        if not field or not isinstance(field, list):
            return None
        try:
            return float(field[0])
        except (ValueError, TypeError):
            return None


async def main() -> None:  # pragma: no cover - manual smoke test utility
    logging.basicConfig(level=logging.INFO)
    client = KrakenTickerClient(pair="XBT/USDT")
    async for update in client.stream():
        LOGGER.info("%s", update)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
