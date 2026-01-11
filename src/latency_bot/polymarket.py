"""Polymarket order book polling and trading utilities."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import (
    ApiCreds,
    OrderArgs,
    OrderBookSummary,
    OrderType,
    PartialCreateOrderOptions,
    ZERO_ADDRESS,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrderBookQuote:
    """Simplified best bid/ask quote representation."""

    best_bid: Optional[float]
    best_bid_size: Optional[float]
    best_ask: Optional[float]
    best_ask_size: Optional[float]
    timestamp_ms: int


class PolymarketClient:
    """Thin wrapper around py-clob-client with asyncio helpers."""

    def __init__(
        self,
        *,
        host: str,
        chain_id: int,
        private_key: str,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
    ) -> None:
        creds = ApiCreds(
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
        )
        self._client = ClobClient(
            host=host,
            chain_id=chain_id,
            key=private_key,
            creds=creds,
        )
        self._lock = asyncio.Lock()
        self._address = self._client.get_address()

    @property
    def address(self) -> str:
        return self._address

    async def get_order_book(self, token_id: str) -> OrderBookSummary:
        return await asyncio.to_thread(self._client.get_order_book, token_id)

    @staticmethod
    def _best_quote(order_book: OrderBookSummary) -> OrderBookQuote:
        best_bid = float(order_book.bids[0].price) if order_book.bids else None
        best_bid_size = float(order_book.bids[0].size) if order_book.bids else None
        best_ask = float(order_book.asks[0].price) if order_book.asks else None
        best_ask_size = float(order_book.asks[0].size) if order_book.asks else None
        return OrderBookQuote(
            best_bid=best_bid,
            best_bid_size=best_bid_size,
            best_ask=best_ask,
            best_ask_size=best_ask_size,
            timestamp_ms=int(float(order_book.timestamp)),
        )

    async def get_best_quote(self, token_id: str) -> OrderBookQuote:
        order_book = await self.get_order_book(token_id)
        return self._best_quote(order_book)

    async def cancel_all(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._client.cancel_all)

    async def place_limit_order(
        self,
        *,
        token_id: str,
        side: str,
        price: float,
        size: float,
        expiration_seconds: int = 60,
        post_only: bool = True,
    ) -> dict:
        side_upper = side.upper()
        if side_upper not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")

        nonce = random.randrange(1, 2**32)
        expiration_ms = int(time.time() * 1000) + expiration_seconds * 1000
        fee_rate_bps = await asyncio.to_thread(self._client.get_fee_rate_bps, token_id)

        order_args = OrderArgs(
            token_id=token_id,
            price=float(price),
            size=float(size),
            side=side_upper,
            fee_rate_bps=int(fee_rate_bps),
            nonce=int(nonce),
            expiration=int(expiration_ms),
            taker=ZERO_ADDRESS,
        )

        async with self._lock:
            signed_order = await asyncio.to_thread(
                self._client.create_order,
                order_args,
                PartialCreateOrderOptions(),
            )
            LOGGER.debug("Posting Polymarket order: %s", signed_order)
            response = await asyncio.to_thread(
                self._client.post_order,
                signed_order,
                OrderType.GTC,
                post_only,
            )
        if hasattr(response, "json"):
            try:
                return response.json()
            except Exception:  # pragma: no cover - fall back to raw response
                return {
                    "status_code": getattr(response, "status_code", None),
                    "text": getattr(response, "text", ""),
                }
        return response


async def get_best_bid_ask(
    client: PolymarketClient,
    yes_token_id: str,
    no_token_id: str,
) -> tuple[OrderBookQuote, OrderBookQuote]:
    """Fetch best bid/ask for YES and NO legs in parallel."""

    yes_task = asyncio.create_task(client.get_best_quote(yes_token_id))
    no_task = asyncio.create_task(client.get_best_quote(no_token_id))
    return await asyncio.gather(yes_task, no_task)
