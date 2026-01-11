"""Configuration models and loading utilities for the latency arbitrage bot."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, SecretStr, ValidationError


class MarketConfig(BaseModel):
    """Per-market threshold configuration."""

    market_id: str = Field(..., description="Polymarket market CLOB ID")
    yes_token_id: str = Field(..., description="YES outcome token id")
    no_token_id: str = Field(..., description="NO outcome token id")
    yes_is_upside: bool = Field(
        True,
        description="Indicates if YES corresponds to the asset finishing higher",
    )
    symbol: str = Field(
        ...,
        description="Kraken trading pair to monitor, e.g. XBT/USDT",
    )
    threshold_pct: float = Field(
        0.02,
        ge=0,
        description="Relative threshold (e.g. 0.02 for 2%) to trigger trades",
    )
    max_position: float = Field(
        500.0,
        ge=0,
        description="Maximum quote currency exposure per direction",
    )


class RiskConfig(BaseModel):
    """Risk management configuration."""

    max_notional_per_trade: float = Field(
        100.0,
        ge=0,
        description="Maximum notional size per trade (USDC)",
    )
    max_trades_per_minute: int = Field(
        60,
        ge=1,
        description="Throttle number of trades per minute to avoid self-slippage",
    )
    self_slippage_buffer_pct: float = Field(
        0.001,
        ge=0,
        description="Buffer applied to Polymarket odds when quoting to mitigate self-slippage",
    )


class Settings(BaseModel):
    """Runtime configuration for the bot."""

    kraken_ws_url: str = Field(
        "wss://ws.kraken.com",
        description="Kraken websocket endpoint",
    )
    kraken_pair: str = Field(
        "XBT/USDT",
        description="Kraken trading pair, e.g. XBT/USD or XBT/USDT",
    )
    polymarket_ws_url: str = Field(
        "wss://ws-subscriptions-clob.polymarket.com/ws",
        description="Polymarket CLOB websocket endpoint",
    )
    polymarket_api_url: str = Field(
        "https://clob.polymarket.com",
        description="Polymarket CLOB REST base URL",
    )
    private_key: SecretStr = Field(..., description="Wallet private key for signing orders")
    api_key: SecretStr = Field(..., description="Polymarket API key")
    api_secret: SecretStr = Field(..., description="Polymarket API secret")
    api_passphrase: SecretStr = Field(..., description="Polymarket API passphrase")
    polygon_rpc_url: Optional[str] = Field(
        None,
        description="Dedicated Polygon RPC endpoint for order settlement",
    )
    polygon_chain_id: int = Field(137, ge=1, description="Polygon chain id (137 for mainnet)")
    markets: list[MarketConfig] = Field(..., min_items=1)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    log_level: str = Field("INFO", regex="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    metrics_port: int = Field(9100, ge=1, le=65535)

CONFIG_ENV_VAR = "LATENCY_BOT_CONFIG"


def load_settings(path: Optional[Path] = None) -> Settings:
    """Load settings from a YAML configuration file."""

    if path is None:
        env_path = os.getenv(CONFIG_ENV_VAR)
        config_path = Path(env_path) if env_path else Path("config.yaml")
    else:
        config_path = path
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file {config_path} not found. Create it before running the bot."
        )
    data = yaml.safe_load(config_path.read_text())
    expanded = _expand_env(data)
    try:
        return Settings.model_validate(expanded)
    except ValidationError as exc:
        detail = exc.json(indent=2)
        raise ValueError(f"Invalid configuration: {detail}") from exc




def _expand_env(value):
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, str):
        return os.path.expandvars(value)
    return value


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings."""

    return load_settings()
