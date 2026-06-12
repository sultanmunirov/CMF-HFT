# Validation Metrics Comparison

This note compares the validation results of two filters:

- `baseline`: same-side Bybit liquidation flow in the last `1s`
- `task3`: Binance large-liquidation filter with `p95` threshold, `20s` window, and `opposite-direction` filtering

Validation period:

- `2026-02-01` to `2026-03-01`

## Summary
The baseline clearly outperforms the simple Task 3 filter on the validation split.

The `task3` filter is much less aggressive:

- it keeps `97.15%` of trades
- it filters only `2.85%` of trades
- it keeps `96.60%` of turnover

By contrast, the baseline is much more selective:

- it keeps `3.54%` of trades
- it filters `96.46%` of trades
- it keeps `6.55%` of turnover

Both filters satisfy the turnover constraint.

## Validation Table
| Horizon | Filter | Kept Share | Filtered Share | Kept Turnover / Day (USD) | PnL All (bps) | PnL Kept (bps) | PnL Filtered (bps) | Score (bps) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 30s | baseline | 0.0354 | 0.9646 | 1,914,383,409.00 | -0.0464 | 3.7637 | -0.3002 | 3.8101 |
| 30s | task3 | 0.9715 | 0.0285 | 28,240,746,507.02 | -0.0464 | -0.0156 | -0.9248 | 0.0308 |
| 120s | baseline | 0.0354 | 0.9646 | 1,914,383,409.00 | -0.0326 | 4.7006 | -0.3478 | 4.7332 |
| 120s | task3 | 0.9715 | 0.0285 | 28,240,746,507.02 | -0.0326 | 0.0433 | -2.1956 | 0.0759 |
| 300s | baseline | 0.0354 | 0.9646 | 1,914,383,409.00 | 0.0245 | 5.6867 | -0.3526 | 5.6622 |
| 300s | task3 | 0.9715 | 0.0285 | 28,240,746,507.02 | 0.0245 | 0.1333 | -3.0766 | 0.1088 |

## Interpretation
The simple Task 3 rule improves the kept-trade PnL relative to the full universe, so its score is positive on all three horizons. However, the effect is weak:

- `+0.0308 bps` at `30s`
- `+0.0759 bps` at `120s`
- `+0.1088 bps` at `300s`

This is far below the baseline:

- `+3.8101 bps` at `30s`
- `+4.7332 bps` at `120s`
- `+5.6622 bps` at `300s`

So, on validation, the current `p95 + 20s + opposite` Task 3 filter is directionally reasonable but not competitive with the baseline.
