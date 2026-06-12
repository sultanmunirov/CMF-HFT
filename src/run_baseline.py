from __future__ import annotations

import argparse
from datetime import timedelta

from tqdm.auto import tqdm

try:
    from src.config import BaselineConfig, source_path
    from src.baseline_utils import (
        MetricsAccumulator,
        add_bbo_mid,
        add_liq_notional,
        build_keep_mask,
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
        build_keep_mask,
        compute_markouts,
        load_window,
        to_us,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Run minimal task 2 baseline")
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
        day_start_with_lookback = day_start - timedelta(seconds=cfg.lookback_s)

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

            bybit_liq_df = add_liq_notional(
                load_window(
                    source_path(cfg, "liq_bybit", symbol),
                    start_us=to_us(day_start_with_lookback),
                    end_us=to_us(day_end),
                    columns=["timestamp", "side", "price", "amount"],
                    timestamp_shift_us=cfg.bybit_delay_us,
                )
            )

            markouts = compute_markouts(trades_df, bbo_df, cfg.horizons_s)
            keep_mask = build_keep_mask(
                trade_ts=trades_df["timestamp"].to_numpy(),
                trade_side=trades_df["side"].to_numpy(),
                bybit_liq_df=bybit_liq_df,
                lookback_s=cfg.lookback_s,
                threshold=cfg.same_side_bybit_threshold,
            )
            accumulator.add_day(trades_df, keep_mask, markouts)

    metrics_df = accumulator.finalize(calendar_day_count=len(day_list))
    output_name = "baseline_metrics.csv" if split == "all" else f"baseline_metrics_{split}.csv"
    output_path = cfg.output_dir / output_name
    metrics_df.write_csv(output_path)
    print(f"Saved metrics to {output_path}")
    print(metrics_df)


if __name__ == "__main__":
    args = parse_args()
    run(split=args.split, limit_days=args.limit_days)
