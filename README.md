# Polymarket Latency Bot Implementation

This repository contains two implementations of a Polymarket latency arbitrage bot:

## 1. Python Implementation (`polymarket_bot_py/`)
A functional, easy-to-understand bot for proving the concept.
- **Features**: 
  - WebSocket streaming from Coinbase/Binance
  - Volatility detection
  - Polymarket CLOB integration
- **Status**: Ready for testing (Dry Run mode active)

## 2. Rust Implementation (`polymarket_bot/`)
A high-performance skeleton for production use.
- **Features**:
  - `tokio` async runtime
  - Minimal latency architecture
  - Multi-stream handling
- **Status**: Core logic and structure implemented

## Setup & Usage

See the `README.md` in each subdirectory for specific instructions.

### Security Warning
**NEVER use compromised keys found in screenshots or public repos.** 
This project relies on `.env` files for security.
