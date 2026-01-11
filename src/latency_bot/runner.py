"""Application entrypoint for the latency arbitrage bot."""

from __future__ import annotations

import asyncio
import logging
import signal

from dotenv import load_dotenv

from .kraken import KrakenTickerClient
from .config import Settings, get_settings
from .polymarket import PolymarketClient
from .strategy import LatencyStrategy


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


async def _run(settings: Settings, stop_event: asyncio.Event) -> None:
    kraken_client = KrakenTickerClient(
        pair=settings.kraken_pair,
        base_ws_url=settings.kraken_ws_url,
    )

    polymarket_client = PolymarketClient(
        host=settings.polymarket_api_url,
        chain_id=settings.polygon_chain_id,
        private_key=settings.private_key.get_secret_value(),
        api_key=settings.api_key.get_secret_value(),
        api_secret=settings.api_secret.get_secret_value(),
        api_passphrase=settings.api_passphrase.get_secret_value(),
    )

    strategy = LatencyStrategy(
        settings=settings,
        kraken_client=kraken_client,
        polymarket_client=polymarket_client,
    )

    await strategy.start()
    try:
        await stop_event.wait()
    finally:
        await strategy.stop()


def main() -> None:
    load_dotenv()
    settings = get_settings()
    _configure_logging(settings.log_level)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    stop_event = asyncio.Event()

    def _handle_signal(sig: signal.Signals) -> None:
        logging.getLogger(__name__).info("Received signal %s", sig.name)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: _handle_signal(s))
        except NotImplementedError:
            signal.signal(sig, lambda *_: _handle_signal(sig))

    try:
        loop.run_until_complete(_run(settings, stop_event))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


if __name__ == "__main__":
    main()
