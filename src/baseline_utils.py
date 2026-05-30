from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import polars as pl


def to_us(dt) -> int:
    return int(dt.timestamp() * 1_000_000)


def load_window(
    path: Path,
    start_us: int,
    end_us: int,
    columns: list[str],
    timestamp_shift_us: int = 0,
) -> pl.DataFrame:
    lf = pl.scan_parquet(path)
    if timestamp_shift_us:
        lf = lf.with_columns((pl.col("timestamp") + timestamp_shift_us).alias("timestamp"))
    return (
        lf.filter((pl.col("timestamp") >= start_us) & (pl.col("timestamp") < end_us))
        .select(columns)
        .collect()
        .sort("timestamp")
    )


def add_bbo_mid(bbo_df: pl.DataFrame) -> pl.DataFrame:
    return bbo_df.with_columns(((pl.col("bid_price") + pl.col("ask_price")) / 2.0).alias("mid"))


def add_liq_notional(liq_df: pl.DataFrame) -> pl.DataFrame:
    return liq_df.with_columns((pl.col("price") * pl.col("amount")).alias("notional"))


def maker_sign_from_taker_side(side: np.ndarray) -> np.ndarray:
    return np.where(side == "buy", 1.0, -1.0)


def compute_markouts(
    trades_df: pl.DataFrame,
    bbo_df: pl.DataFrame,
    horizons_s: tuple[int, ...],
) -> dict[str, np.ndarray]:
    trade_ts = trades_df["timestamp"].to_numpy()
    trade_price = trades_df["price"].to_numpy()
    taker_side = trades_df["side"].to_numpy()
    maker_sign = maker_sign_from_taker_side(taker_side)

    bbo_ts = bbo_df["timestamp"].to_numpy()
    bbo_mid = bbo_df["mid"].to_numpy()

    out: dict[str, np.ndarray] = {"maker_sign": maker_sign}

    idx_now = np.searchsorted(bbo_ts, trade_ts, side="right") - 1
    out["mid_t"] = np.full(len(trade_ts), np.nan)
    valid_now = (idx_now >= 0) & (trade_ts >= bbo_ts[0])
    out["mid_t"][valid_now] = bbo_mid[idx_now[valid_now]]

    for tau in horizons_s:
        target_ts = trade_ts + tau * 1_000_000
        idx_future = np.searchsorted(bbo_ts, target_ts, side="right") - 1
        valid = (idx_future >= 0) & (target_ts >= bbo_ts[0]) & (target_ts <= bbo_ts[-1])

        mid_future = np.full(len(trade_ts), np.nan)
        mid_future[valid] = bbo_mid[idx_future[valid]]

        pnl = np.full(len(trade_ts), np.nan)
        pnl[valid] = (
            -maker_sign[valid] * (mid_future[valid] - trade_price[valid]) / trade_price[valid] * 10000.0 + 0.5
        )

        out[f"mid_future_{tau}s"] = mid_future
        out[f"pnl_{tau}s"] = pnl

    return out


def rolling_event_sum(
    trade_ts: np.ndarray,
    event_ts: np.ndarray,
    event_values: np.ndarray,
    lookback_s: int,
) -> np.ndarray:
    if len(event_ts) == 0:
        return np.zeros(len(trade_ts), dtype=np.float64)

    window_us = lookback_s * 1_000_000
    left_idx = np.searchsorted(event_ts, trade_ts - window_us, side="left")
    right_idx = np.searchsorted(event_ts, trade_ts, side="right")

    csum = np.concatenate(([0.0], np.cumsum(event_values, dtype=np.float64)))
    return csum[right_idx] - csum[left_idx]


def compute_same_side_liq_feature(
    trade_ts: np.ndarray,
    trade_side: np.ndarray,
    liq_df: pl.DataFrame,
    lookback_s: int,
) -> np.ndarray:
    buy_liq = liq_df.filter(pl.col("side") == "buy")
    sell_liq = liq_df.filter(pl.col("side") == "sell")

    buy_sum = rolling_event_sum(
        trade_ts,
        buy_liq["timestamp"].to_numpy(),
        buy_liq["notional"].to_numpy(),
        lookback_s,
    )
    sell_sum = rolling_event_sum(
        trade_ts,
        sell_liq["timestamp"].to_numpy(),
        sell_liq["notional"].to_numpy(),
        lookback_s,
    )
    return np.where(trade_side == "buy", buy_sum, sell_sum)


def build_keep_mask(
    trade_ts: np.ndarray,
    trade_side: np.ndarray,
    bybit_liq_df: pl.DataFrame,
    lookback_s: int,
    threshold: float,
) -> np.ndarray:
    same_side_bybit = compute_same_side_liq_feature(trade_ts, trade_side, bybit_liq_df, lookback_s)
    return same_side_bybit > threshold


@dataclass
class HorizonAccumulator:
    weighted_pnl_all: float = 0.0
    weighted_pnl_kept: float = 0.0
    weighted_pnl_filtered: float = 0.0
    weight_all: float = 0.0
    weight_kept: float = 0.0
    weight_filtered: float = 0.0


@dataclass
class MetricsAccumulator:
    horizons_s: tuple[int, ...]
    turnover_constraint_usd_per_day: float
    row_count: int = 0
    kept_row_count: int = 0
    filtered_row_count: int = 0
    total_notional: float = 0.0
    kept_notional: float = 0.0
    filtered_notional: float = 0.0
    per_horizon: dict[int, HorizonAccumulator] = field(default_factory=dict)

    def __post_init__(self):
        if not self.per_horizon:
            self.per_horizon = {tau: HorizonAccumulator() for tau in self.horizons_s}

    def add_day(
        self,
        trades_df: pl.DataFrame,
        keep_mask: np.ndarray,
        markouts: dict[str, np.ndarray],
    ) -> None:
        notional = (trades_df["price"].to_numpy() * trades_df["amount"].to_numpy()).astype(np.float64)
        weights = np.minimum(notional, 100_000.0)

        self.row_count += len(trades_df)
        self.kept_row_count += int(keep_mask.sum())
        self.filtered_row_count += int((~keep_mask).sum())
        self.total_notional += float(notional.sum())
        self.kept_notional += float(notional[keep_mask].sum())
        self.filtered_notional += float(notional[~keep_mask].sum())

        for tau in self.horizons_s:
            pnl = markouts[f"pnl_{tau}s"]
            valid = np.isfinite(pnl)

            if valid.any():
                self.per_horizon[tau].weighted_pnl_all += float((pnl[valid] * weights[valid]).sum())
                self.per_horizon[tau].weight_all += float(weights[valid].sum())

            kept_valid = valid & keep_mask
            if kept_valid.any():
                self.per_horizon[tau].weighted_pnl_kept += float((pnl[kept_valid] * weights[kept_valid]).sum())
                self.per_horizon[tau].weight_kept += float(weights[kept_valid].sum())

            filtered_valid = valid & (~keep_mask)
            if filtered_valid.any():
                self.per_horizon[tau].weighted_pnl_filtered += float((pnl[filtered_valid] * weights[filtered_valid]).sum())
                self.per_horizon[tau].weight_filtered += float(weights[filtered_valid].sum())

    def finalize(self, calendar_day_count: int) -> pl.DataFrame:
        rows = []
        filtered_share = self.filtered_row_count / self.row_count if self.row_count else float("nan")
        kept_share = self.kept_row_count / self.row_count if self.row_count else float("nan")
        kept_turnover_share = self.kept_notional / self.total_notional if self.total_notional else float("nan")
        kept_turnover_per_day = self.kept_notional / calendar_day_count if calendar_day_count else float("nan")

        for tau, acc in self.per_horizon.items():
            pnl_all = acc.weighted_pnl_all / acc.weight_all if acc.weight_all else float("nan")
            pnl_kept = acc.weighted_pnl_kept / acc.weight_kept if acc.weight_kept else float("nan")
            pnl_filtered = acc.weighted_pnl_filtered / acc.weight_filtered if acc.weight_filtered else float("nan")
            rows.append(
                {
                    "horizon_s": tau,
                    "rows_total": self.row_count,
                    "kept_share": kept_share,
                    "filtered_share": filtered_share,
                    "kept_turnover_share": kept_turnover_share,
                    "kept_turnover_usd_per_day": kept_turnover_per_day,
                    "turnover_constraint_usd_per_day": self.turnover_constraint_usd_per_day,
                    "turnover_constraint_met": kept_turnover_per_day >= self.turnover_constraint_usd_per_day,
                    "PnL_all_bps": pnl_all,
                    "PnL_kept_bps": pnl_kept,
                    "PnL_filtered_bps": pnl_filtered,
                    "Score_bps": pnl_kept - pnl_all,
                }
            )
        return pl.DataFrame(rows)
