from __future__ import annotations

import argparse
from datetime import timedelta

import numpy as np
import polars as pl
from tqdm.auto import tqdm

try:
    from src.config import BaselineConfig, source_path
    from src.baseline_utils import (
        MetricsAccumulator,
        add_bbo_mid,
        add_liq_notional,
        compute_markouts,
        load_window,
        to_us,
    )
except ModuleNotFoundError:
    from config import BaselineConfig, source_path
    from baseline_utils import (
        MetricsAccumulator,
        add_bbo_mid,
        add_liq_notional,
        compute_markouts,
        load_window,
        to_us,
    )


P95_LIQ_THRESHOLD_USD = 34_801.32
WINDOW_SECONDS = 20


def parse_args():
    parser = argparse.ArgumentParser(description="Run simple task 3 liquidation filter")
    parser.add_argument(
        "--split",
        choices=("train", "validation", "all"),
        default="all",
        help="Dataset split to process",
    )
    parser.add_argument(
        "--limit-days",
        type=int,
        default=None,
        help="Process only the first N days of the selected split",
    )
    return parser.parse_args()


def rolling_event_count(
    trade_ts: np.ndarray,
    event_ts: np.ndarray,
    window_s: int,
) -> np.ndarray:
    if len(event_ts) == 0:
        return np.zeros(len(trade_ts), dtype=np.int64)

    window_us = window_s * 1_000_000
    left_idx = np.searchsorted(event_ts, trade_ts - window_us, side="left")
    right_idx = np.searchsorted(event_ts, trade_ts, side="right")
    return right_idx - left_idx


def build_keep_mask(
    trade_ts: np.ndarray,
    trade_side: np.ndarray,
    liq_df: pl.DataFrame,
    liq_threshold_usd: float,
    window_seconds: int,
) -> np.ndarray:
    large_liq_df = liq_df.filter(pl.col("notional") >= liq_threshold_usd)
    if large_liq_df.is_empty():
        return np.ones(len(trade_ts), dtype=bool)

    buy_liq_ts = large_liq_df.filter(pl.col("side") == "buy")["timestamp"].to_numpy()
    sell_liq_ts = large_liq_df.filter(pl.col("side") == "sell")["timestamp"].to_numpy()

    opposite_buy_trade = rolling_event_count(trade_ts, sell_liq_ts, window_seconds)
    opposite_sell_trade = rolling_event_count(trade_ts, buy_liq_ts, window_seconds)

    filter_mask = np.where(trade_side == "buy", opposite_buy_trade > 0, opposite_sell_trade > 0)
    return ~filter_mask


def run(split: str = "all", limit_days: int | None = None) -> None:
    cfg = BaselineConfig()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    accumulator = MetricsAccumulator(
        horizons_s=cfg.horizons_s,
        turnover_constraint_usd_per_day=cfg.turnover_constraint_usd_per_day,
    )

    day_list = list(cfg.iter_days(split=split))
    if limit_days is not None:
        day_list = day_list[:limit_days]

    for day_start in tqdm(day_list, desc="Days"):
        day_end = day_start + timedelta(days=1)
        day_end_with_horizon = day_end + timedelta(seconds=cfg.max_horizon_s)

        for symbol in tqdm(cfg.symbols, desc="Symbols", leave=False):
            trades_df = load_window(
                source_path(cfg, "trades", symbol),
                start_us=to_us(day_start),
                end_us=to_us(day_end),
                columns=["timestamp", "side", "price", "amount"],
            )
            if trades_df.is_empty():
                continue

            bbo_df = add_bbo_mid(
                load_window(
                    source_path(cfg, "bbo", symbol),
                    start_us=to_us(day_start - timedelta(days=1)),
                    end_us=to_us(day_end_with_horizon),
                    columns=["timestamp", "bid_price", "ask_price", "bid_amount", "ask_amount"],
                )
            )
            if bbo_df.is_empty():
                continue

            liq_df = add_liq_notional(
                load_window(
                    source_path(cfg, "liq_binance", symbol),
                    start_us=to_us(day_start),
                    end_us=to_us(day_end),
                    columns=["timestamp", "side", "price", "amount"],
                )
            )

            markouts = compute_markouts(trades_df, bbo_df, cfg.horizons_s)
            keep_mask = build_keep_mask(
                trade_ts=trades_df["timestamp"].to_numpy(),
                trade_side=trades_df["side"].to_numpy(),
                liq_df=liq_df,
                liq_threshold_usd=P95_LIQ_THRESHOLD_USD,
                window_seconds=WINDOW_SECONDS,
            )
            accumulator.add_day(trades_df, keep_mask, markouts)

    metrics_df = accumulator.finalize(calendar_day_count=len(day_list))
    metrics_df = metrics_df.with_columns(
        pl.lit("binance").alias("liq_source"),
        pl.lit(P95_LIQ_THRESHOLD_USD).alias("liq_threshold_usd"),
        pl.lit(WINDOW_SECONDS).alias("window_seconds"),
        pl.lit("opposite").alias("filter_direction"),
    )

    output_name = "task3_metrics.csv" if split == "all" else f"task3_metrics_{split}.csv"
    output_path = cfg.output_dir / output_name
    metrics_df.write_csv(output_path)
    print(f"Saved metrics to {output_path}")
    print(metrics_df)


if __name__ == "__main__":
    args = parse_args()
    run(split=args.split, limit_days=args.limit_days)
