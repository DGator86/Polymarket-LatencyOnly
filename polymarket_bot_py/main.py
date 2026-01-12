import asyncio
import json
import os
import sys
print("Starting bot...")
import time
import logging
from collections import deque
from typing import Optional, Dict, Any

import websockets
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PolyBot")

# Load Environment Variables
load_dotenv()

# --- CONFIGURATION ---
BINANCE_WS_URL = "wss://ws-feed.exchange.coinbase.com" # Using Coinbase due to geo-blocking
SYMBOL = "BTC"
THRESHOLD_PERCENT = 0.002
TIME_WINDOW_SECONDS = 5
POLL_INTERVAL_MS = 100
DRY_RUN = True

DUMMY_PRIVATE_KEY = "0x" + "0" * 64
DUMMY_API_KEY = "00000000-0000-0000-0000-000000000000"
DUMMY_API_SECRET = "0" * 64
DUMMY_API_PASSPHRASE = "your_passphrase"


def env_or_dummy(name: str, dummy_value: str) -> str:
    value = os.getenv(name)
    if not value:
        logger.warning("Missing %s env var; using dummy placeholder.", name)
        return dummy_value
    return value

# ... (Security Check remains) ...

class BinanceTracker:
    def __init__(self):
        self.current_price: float = 0.0
        self.price_history = deque()

    async def connect_and_listen(self):
        async with websockets.connect(BINANCE_WS_URL) as websocket:
            logger.info("Connected to Coinbase WebSocket")
            
            # Subscribe to BTC-USD ticker
            subscribe_msg = {
                "type": "subscribe",
                "product_ids": ["BTC-USD"],
                "channels": ["ticker"]
            }
            await websocket.send(json.dumps(subscribe_msg))
            
            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    
                    if data.get("type") == "ticker" and "price" in data:
                        price = float(data['price'])
                        timestamp = time.time()
                        
                        self.current_price = price
                        self.price_history.append((timestamp, price))
                        self._cleanup_history(timestamp)
                        
                except Exception as e:
                    logger.error(f"WebSocket Error: {e}")
                    await asyncio.sleep(1) 

    def _cleanup_history(self, current_time):
        while self.price_history and (current_time - self.price_history[0][0] > TIME_WINDOW_SECONDS):
            self.price_history.popleft()

    def get_price_change(self) -> float:
        """Returns percentage change over the time window."""
        if not self.price_history:
            return 0.0
        
        oldest_price = self.price_history[0][1]
        if oldest_price == 0: return 0.0
        
        return (self.current_price - oldest_price) / oldest_price

class PolyClientWrapper:
    def __init__(self):
        self.host = os.getenv("POLY_HOST", "https://clob.polymarket.com")
        self.key = env_or_dummy("POLY_KEY", DUMMY_PRIVATE_KEY)
        self.chain_id = int(os.getenv("CHAIN_ID", 137))
        self.creds = ApiCreds(
            api_key=env_or_dummy("POLY_API_KEY", DUMMY_API_KEY),
            api_secret=env_or_dummy("POLY_API_SECRET", DUMMY_API_SECRET),
            api_passphrase=env_or_dummy("POLY_API_PASSPHRASE", DUMMY_API_PASSPHRASE)
        )
        
        try:
            self.client = ClobClient(
                self.host,
                key=self.key,
                chain_id=self.chain_id,
                creds=self.creds
            )
            logger.info("Initialized Polymarket CLOB Client")
        except Exception as e:
            logger.error(f"Failed to init CLOB client: {e}")
            self.client = None

    async def get_market_odds(self, condition_id: str) -> Optional[float]:
        # Implementation would fetch orderbook and calculate mid-price
        # Simplified for demo:
        try:
            if not self.client: return 0.5
            # This is a synchronous call in the library, might block. 
            # In production, use run_in_executor or the library's async support if available.
            # ob = self.client.get_order_book(condition_id)
            # return self._calculate_mid_price(ob)
            return 0.5 # Dummy return
        except Exception as e:
            logger.error(f"Error fetching odds: {e}")
            return None

    async def place_order(self, token_id: str, side: str, price: float, size: float):
        if DRY_RUN:
            logger.info(f"[DRY RUN] Placing {side} order on {token_id} @ {price}, size: {size}")
            return
            
        try:
            # Construct order args
            # resp = self.client.create_and_post_order(...)
            logger.info(f"Order placed: {side} {token_id}")
        except Exception as e:
            logger.error(f"Order failed: {e}")

async def main():
    tracker = BinanceTracker()
    poly = PolyClientWrapper()
    
    # Start Binance listener in background
    asyncio.create_task(tracker.connect_and_listen())
    
    logger.info("Bot started. Waiting for market data...")
    await asyncio.sleep(2) # Warmup
    
    while True:
        try:
            # 1. Check Binance Moves
            pct_change = tracker.get_price_change()
            
            # Log periodic status
            if int(time.time()) % 10 == 0:
                logger.info(f"Current BTC: {tracker.current_price:.2f} | Change({TIME_WINDOW_SECONDS}s): {pct_change*100:.4f}%")
            
            # 2. Threshold Check
            if abs(pct_change) > THRESHOLD_PERCENT:
                direction = "UP" if pct_change > 0 else "DOWN"
                logger.warning(f"🚨 ALERT: Binance moved {direction} by {pct_change*100:.4f}%! Checking Polymarket...")
                
                # 3. Arbitrage Logic (Simplified)
                # In a real bot, you would:
                # a) Identify the active 15-min BTC market ID
                # b) Fetch current Yes/No odds
                # c) Compare implied probability vs new spot price
                # d) Execute trade
                
                # Example Action
                if direction == "UP":
                    # Buy 'Yes' on BTC Up
                    await poly.place_order("DUMMY_TOKEN_ID_YES", "BUY", 0.60, 100)
                else:
                    # Buy 'Yes' on BTC Down (or 'No' on Up)
                    await poly.place_order("DUMMY_TOKEN_ID_NO", "BUY", 0.60, 100)
                
                # Cooldown to avoid spamming same move
                await asyncio.sleep(5) 
                
            await asyncio.sleep(POLL_INTERVAL_MS / 1000)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
