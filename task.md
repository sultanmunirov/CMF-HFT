# HW3: Large Liquidation Reaction Filter

## Goal
Goal of this week is to create filter for large liquidations:

## Visualize the reaction (EDA)
For each large liquidation build the following plot:

- X axis: time after the liquidation, from 0 to 300 seconds
- Y axis: average markout of Binance trades (use τ=30s) that fall within this window

Plot two separate curves:

- trades in the same direction as the liquidation
- trades in the opposite direction

Average across all large liquidations. Find visually: after how many seconds does the reaction fade? Where is the peak?

Define "large liquidation" yourself — try several thresholds (e.g. 90th, 95th, 99th percentile by notional) and see how the picture changes.

## Build the filter
Based on your plots, choose two parameters:

- liq_threshold — minimum liquidation size (in USD) to count as large
- window_seconds — how many seconds after a liquidation to filter trades

Filter logic: if a trade falls in the window [t_liq, t_liq + window_seconds] after a large liquidation and its direction matches the direction of the liquidation — filter it (f_i = 1).

Implement this as a function following the format from description.md.

## Measure
Compute on both train and validation splits:

- Score(τ) for τ ∈ {30s, 120s, 300s}
- PnL_kept, PnL_filtered
- KeptTurnoverPerDay (make sure it stays ≥ 500k$/day)

Compare against your baseline from Task 2.

## Deliverables
- Jupyter notebook with code and plots
- Metrics table for train / validation
