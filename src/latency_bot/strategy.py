"""Strategy logic for Polymarket latency arbitrage."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from typing import Dict, List

from .kraken import KrakenTicker, KrakenTickerClient
from .config import MarketConfig, RiskConfig, Settings
from .polymarket import OrderBookQuote, PolymarketClient, get_best_bid_ask

LOGGER = logging.getLogger(__name__)


@dataclass
class MarketState:
    config: MarketConfig
    reference_price: float | None = None
    last_trade_ts: float = 0.0
    trades_in_minute: int = 0
    minute_bucket: int = 0
    position: float = 0.0

    def update_reference(self, price: float) -> None:
        self.reference_price = price

    def can_trade(self, now: float, max_trades_per_minute: int) -> bool:
        minute = int(now // 60)
        if minute != self.minute_bucket:
            self.minute_bucket = minute
            self.trades_in_minute = 0
        if self.trades_in_minute >= max_trades_per_minute:
            return False
        return True

    def register_trade(self, amount: float, now: float) -> None:
        self.last_trade_ts = now
        self.trades_in_minute += 1
        self.position += amount

    def reset_position(self) -> None:
        self.position = 0.0


class LatencyStrategy:
    """Consumes Kraken ticks and reacts on Polymarket order books."""

    def __init__(
        self,
        *,
        settings: Settings,
        kraken_client: KrakenTickerClient,
        polymarket_client: PolymarketClient,
    ) -> None:
        self._settings = settings
        self._kraken_client = kraken_client
        self._polymarket_client = polymarket_client

        self._symbol_markets: Dict[str, List[MarketState]] = {}
        for market in settings.markets:
            self._symbol_markets.setdefault(market.symbol.lower(), []).append(
                MarketState(config=market)
            )

        self._risk = settings.risk
        self._tasks: list[asyncio.Task] = []
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        LOGGER.info("Starting latency strategy for %d markets", len(self._symbol_markets))
        task = asyncio.create_task(self._consume_kraken())
        self._tasks.append(task)

    async def stop(self) -> None:
        LOGGER.info("Stopping latency strategy")
        self._stopping.set()
        await self._kraken_client.stop()
        for task in self._tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._polymarket_client.cancel_all()

    async def _consume_kraken(self) -> None:
        async for ticker in self._kraken_client.stream():
            if self._stopping.is_set():
                break
            await self._handle_kraken_tick(ticker)

    async def _handle_kraken_tick(self, ticker: KrakenTicker) -> None:
        symbol = ticker.pair.lower()
        markets = self._symbol_markets.get(symbol, [])
        if not markets:
            return
        for state in markets:
            await self._process_market(state, ticker)

    async def _process_market(self, state: MarketState, ticker: KrakenTicker) -> None:
        price = ticker.price
        if state.reference_price is None:
            state.update_reference(price)
            return

        reference = state.reference_price
        if reference <= 0:
            state.update_reference(price)
            return

        delta = (price - reference) / reference
        threshold = state.config.threshold_pct
        if abs(delta) < threshold:
            return

        now = time.time()
        if not state.can_trade(now, self._risk.max_trades_per_minute):
            return

        yes_quote, no_quote = await get_best_bid_ask(
            self._polymarket_client,
            state.config.yes_token_id,
            state.config.no_token_id,
        )

        direction = "up" if delta > 0 else "down"
        quote, token_id = self._select_quote(state, yes_quote, no_quote, direction)
        if quote is None:
            LOGGER.debug("No liquidity for market %s", state.config.market_id)
            state.update_reference(price)
            return

        side = "BUY"

        target_price = self._determine_target_price(quote, side)
        if target_price is None:
            LOGGER.debug("Missing target price for market %s", state.config.market_id)
            state.update_reference(price)
            return

        size = self._compute_order_size(quote, state.config, self._risk, side)
        if size <= 0:
            LOGGER.debug("Computed size 0 for market %s", state.config.market_id)
            state.update_reference(price)
            return

        remaining_notional = state.config.max_position - state.position
        if remaining_notional <= 0:
            LOGGER.debug("Max position reached for market %s", state.config.market_id)
            state.update_reference(price)
            return
        max_size_by_position = remaining_notional / max(target_price, 1e-6)
        size = min(size, max_size_by_position)
        if size <= 0:
            LOGGER.debug("No remaining size capacity for market %s", state.config.market_id)
            state.update_reference(price)
            return

        LOGGER.info(
            "Triggering %s trade on %s: delta=%.4f price=%.2f target=%.4f size=%.2f",
            direction,
            state.config.market_id,
            delta,
            price,
            target_price,
            size,
        )
        try:
            response = await self._polymarket_client.place_limit_order(
                token_id=token_id,
                side=side,
                price=target_price,
                size=size,
                post_only=False,
            )
            LOGGER.info("Order response %s", response)
            state.register_trade(size * target_price, now)
            state.update_reference(price)
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Failed to place order: %s", exc)
            state.update_reference(price)

    def _determine_target_price(
        self, quote: OrderBookQuote, side: str
    ) -> float | None:
        buffer = self._risk.self_slippage_buffer_pct
        if side == "BUY":
            if quote.best_ask is None:
                return None
            return min(1.0, quote.best_ask * (1 + buffer))
        if side == "SELL":
            if quote.best_bid is None:
                return None
            return max(0.0, quote.best_bid * (1 - buffer))
        return None

    def _compute_order_size(
        self,
        quote: OrderBookQuote,
        market: MarketConfig,
        risk: RiskConfig,
        side: str,
    ) -> float:
        if side == "BUY":
            book_size = quote.best_ask_size
        else:
            book_size = quote.best_bid_size
        if book_size is None:
            book_size = quote.best_bid_size if side == "BUY" else quote.best_ask_size
        max_size = min(market.max_position, risk.max_notional_per_trade)
        if book_size is None:
            return max_size
        return min(book_size, max_size)

    def _select_quote(
        self,
        state: MarketState,
        yes_quote: OrderBookQuote,
        no_quote: OrderBookQuote,
        direction: str,
    ) -> tuple[OrderBookQuote | None, str]:
        if direction == "up":
            if state.config.yes_is_upside:
                return yes_quote, state.config.yes_token_id
            return no_quote, state.config.no_token_id
        else:
            if state.config.yes_is_upside:
                return no_quote, state.config.no_token_id
            return yes_quote, state.config.yes_token_id
