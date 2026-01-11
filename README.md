# Polymarket Latency Arbitrage Bot

⚠️ **High risk tooling** – trading with leverage and private keys can incur irreversible financial losses. Run this software only if you fully understand Polymarket's rules, custodial risks, the Polygon network, and the operational/security implications of automated trading. Use a freshly generated wallet, keep private keys offline, rate-limit access, and never hard-code secrets into source control.

## Overview

This project implements a research-grade reference bot that listens to Kraken spot price movements and attempts to exploit short-lived mispricings on Polymarket binary markets. It:

- Streams real-time Kraken ticker data via WebSocket
- Polls Polymarket order books via the official [`py-clob-client`](https://pypi.org/project/py-clob-client/) SDK
- Applies configurable latency thresholds to decide when to aggress stale Polymarket quotes
- Places signed CLOB orders with authenticated API credentials
- Enforces basic per-market risk throttles (max notional, trades/minute, self-slippage buffer)

💡 The logic is intentionally modular so you can extend it with your own predictive signals, monitoring, and post-trade analytics.

## Prerequisites

- Python 3.10+
- Polymarket account with Level 2 API credentials (API key / secret / passphrase)
- Polygon RPC endpoint with sufficient throughput
- Dedicated VPS located close to Polymarket infrastructure (recommended)
- WebSocket connectivity to Kraken (consider dedicated feeds for production)

## Quick Start

1. **Clone & install dependencies**
   ```bash
   cd /path/to/repo
   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -e .[dev]
   ```

2. **Create a private config**
   ```bash
   cp config.example.yaml config.yaml
   ```
   Edit `config.yaml` and replace placeholder values with your market IDs and token IDs. Secrets can be injected via environment variables (e.g. set `PRIVATE_KEY`, `POLYMARKET_API_KEY`, etc.) before launching; `${VAR}` placeholders will be expanded automatically.

   > ⚠️ Never commit `config.yaml` or raw keys. Use a dedicated wallet with strictly limited funds. Rotate credentials frequently.

3. **Export environment variables (optional)**
   ```bash
   export PRIVATE_KEY=0x...   # NEVER paste production keys into shared shells
   export POLYMARKET_API_KEY=...
   export POLYMARKET_API_SECRET=...
   export POLYMARKET_API_PASSPHRASE=...
   ```

4. **Run the bot**
   ```bash
   polymarket-latency-bot
   ```
   or set an alternate config path:
   ```bash
   LATENCY_BOT_CONFIG=/secure/path/bot-config.yaml polymarket-latency-bot
   ```

5. **Stop safely**
   Use `Ctrl+C` or send `SIGINT/SIGTERM`. The runner will cancel outstanding tasks and issue a `cancel_all` request to Polymarket.

## Configuration Guide

Key fields inside `config.yaml`:

| Field | Description |
|-------|-------------|
| `kraken_pair` | Trading pair for Kraken feed (e.g. `XBT/USDT`). |
| `markets[]` | A list of per-market settings. Each entry requires the market CLOB ID, YES/NO token IDs, and whether YES represents the upside move. |
| `threshold_pct` | Minimum relative Kraken move before the bot attempts to trade. |
| `max_position` | Per-market risk ceiling (USDC notionals). Combined with `risk.max_notional_per_trade`. |
| `risk.self_slippage_buffer_pct` | Buffer applied to the best quote before crossing, mitigating self-slippage. |

Refer to `config.example.yaml` for a full template.

## Operational Notes

- **Latency matters**: use colocated infrastructure and dedicated Polygon RPC. Public RPCs will bottleneck.
- **Order throttling**: `risk.max_trades_per_minute` avoids flooding the books; tune carefully.
- **Position tracking**: the sample strategy only accumulates inventory; implement exit/hedging logic before deploying real capital.
- **Monitoring**: integrate with Prometheus/Grafana or your observability stack. Exported metrics port is reserved (`metrics_port`) for future work.

## Security Best Practices

- Protect your wallet private key. Treat any machine running this bot as sensitive infrastructure.
- Audit third-party libraries (`py-clob-client`, etc.) and pin versions before production use.
- Validate that the Polymarket API credentials you load have only the permissions you intend.
- Consider hardware security modules (HSM) or remote signing instead of raw private keys.

## Disclaimer

This repository is provided **as-is** for educational purposes. There is no guarantee of profitability. Markets evolve quickly; latency advantages decay as other participants deploy similar strategies. Test thoroughly on small sizes, monitor for self-slippage, and comply with all venue terms of service and regulatory obligations in your jurisdiction.
