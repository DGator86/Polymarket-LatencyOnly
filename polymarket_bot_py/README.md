# Polymarket Latency Bot

This project implements a latency arbitrage bot for Polymarket, targeting the delay between spot price moves (Binance/Coinbase) and Polymarket order book updates.

## ⚠️ CRITICAL SECURITY WARNING

**NEVER SHARE YOUR PRIVATE KEYS.** The private key shown in the original screenshot is COMPROMISED. Do not use it.
Always load keys from environment variables (`.env`) and never commit them to version control.

## Prerequisites

- **Python 3.10+**
- **Polymarket API Keys** (generate via https://docs.polymarket.com/developers/market-makers/setup#api-key-generation)
- **Polygon RPC Node** (Dedicated node recommended for speed)
- **VPS Location**: Amsterdam (to minimize latency to Polymarket servers)

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment:
   Copy `.env.example` to `.env` and fill in your details:
   ```bash
   cp .env.example .env
   ```
   
   **Required variables:**
   - `POLY_KEY`: Your Polygon wallet private key (starts with 0x...)
   - `POLY_API_KEY`: API Key from Polymarket
   - `POLY_API_SECRET`: API Secret
   - `POLY_API_PASSPHRASE`: API Passphrase

## Generate API credentials (optional helper)

If you need to create API credentials from your wallet private key, you can use
`py_clob_client` directly:

```python
from py_clob_client.client import ClobClient
import os

host = "https://clob.polymarket.com"
key = os.getenv("POLY_KEY")
chain_id = 137

client = ClobClient(host, key=key, chain_id=chain_id)
credentials = client.create_or_derive_api_creds()
print(credentials.api_key, credentials.api_secret, credentials.passphrase)
```

## Strategy Logic

1. **Spot Price Tracking**: Connects to Coinbase Pro WebSocket (faster/easier than Binance for US users, but code supports switching) to stream `BTC-USD` prices.
2. **Volatility Detection**: Calculates percentage change over a sliding window (default 5 seconds).
3. **Threshold Trigger**: If price moves > `THRESHOLD_PERCENT` (e.g., 0.2%), it checks Polymarket.
4. **Execution**: Places Limit Orders on the stale side of the order book.

## Usage

Run the bot:
```bash
python3 main.py
```

## Optimization Tips (from "The Edge")

- **Infrastructure**: Run this on a VPS in Amsterdam.
- **RPC**: Use a paid, private Polygon RPC endpoint in `py-clob-client` config (edit `main.py` to pass `rpc_url` if supported or configure in env).
- **Rust Port**: For <50ms reaction times, port `main.py` to Rust using `tokio` and `tungstenite`.

## Disclaimer

This software is for educational purposes only. Trading involves risk. Use at your own risk.
