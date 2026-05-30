# Task 2 Solution

## Filter description

This baseline uses a very simple rule based on recent Bybit liquidation flow.

For each Binance trade:

- if the trade side is `buy`, we look at Bybit `buy` liquidations in the last `1s`
- if the trade side is `sell`, we look at Bybit `sell` liquidations in the last `1s`

The filter keeps the trade only if recent same-side Bybit liquidation notional is nonzero.

Equivalently:

- taker `buy` -> keep only if recent Bybit `buy` liquidation flow exists
- taker `sell` -> keep only if recent Bybit `sell` liquidation flow exists

Bybit liquidation timestamps are shifted by `+200 ms` before feature construction, following the task convention.

## Timeline

The baseline is evaluated on the available public period:

- start: `2025-12-01`
- end: `2026-02-28`

The signal is scored on three markout horizons:

- `30s`
- `120s`
- `300s`

## Metrics

For each horizon, the following metrics are reported:

- `PnL_all_bps`
- `PnL_kept_bps`
- `PnL_filtered_bps`
- `Score_bps = PnL_kept_bps - PnL_all_bps`
- `kept_share`
- `filtered_share`
- `kept_turnover_share`
- `kept_turnover_usd_per_day`
- `turnover_constraint_met`

The turnover constraint is:

```text
kept_turnover_usd_per_day >= 500,000
```

## Output

The resulting metrics are saved to:

```text
outputs/baseline_metrics.csv
```

## Baseline Metrics

| horizon_s | rows_total | kept_share | filtered_share | turnover_constraint_met | PnL_all_bps | PnL_kept_bps | PnL_filtered_bps | Score_bps |
|---|---:|---:|---:|---|---:|---:|---:|---:|
| 30 | 1107782898 | 0.035219 | 0.964781 | true | -0.061340 | 2.973088 | -0.256158 | 3.034428 |
| 120 | 1107782898 | 0.035219 | 0.964781 | true | 0.023853 | 4.281416 | -0.249495 | 4.257563 |
| 300 | 1107782898 | 0.035219 | 0.964781 | true | 0.077268 | 4.483198 | -0.205608 | 4.405931 |
