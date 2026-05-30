from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class BaselineConfig:
    repo_root: Path = Path(__file__).resolve().parents[1]
    data_root: Path = repo_root / "data"
    output_dir: Path = repo_root / "outputs"

    train_start: datetime = datetime(2025, 12, 1, tzinfo=timezone.utc)
    train_end_exclusive: datetime = datetime(2026, 3, 1, tzinfo=timezone.utc)

    symbols: tuple[str, ...] = ("btcusdt", "ethusdt")
    horizons_s: tuple[int, ...] = (30, 120, 300)

    bybit_delay_us: int = 200_000
    lookback_s: int = 1
    turnover_constraint_usd_per_day: float = 500_000.0

    # Top simple signal from the EDA:
    # keep if same-side Bybit liquidation flow in the last 1 second is nonzero
    same_side_bybit_threshold: float = 0.0

    @property
    def max_horizon_s(self) -> int:
        return max(self.horizons_s)

    @property
    def num_days(self) -> int:
        return (self.train_end_exclusive - self.train_start).days

    def iter_days(self):
        current = self.train_start
        one_day = timedelta(days=1)
        while current < self.train_end_exclusive:
            yield current
            current += one_day


def source_path(cfg: BaselineConfig, source: str, symbol: str) -> Path:
    if source == "trades":
        return cfg.data_root / "binance_trades" / f"perp_{symbol}.parquet"
    if source == "bbo":
        return cfg.data_root / "binance_booktickers" / f"perp_{symbol}.parquet"
    if source == "liq_binance":
        return cfg.data_root / "binance_liquidations" / f"perp_{symbol}.parquet"
    if source == "liq_bybit":
        return cfg.data_root / "bybit_liquidations" / f"{symbol}.parquet"
    raise ValueError(f"Unknown source: {source}")
