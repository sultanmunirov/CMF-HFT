# Trade Filtering Task

You are given 3 months of data:

- `binance`: trades, BBO, liquidations
- `bybit`: liquidations

The goal is to build a signal that filters `binance` trades, assuming that we are collecting fills as a maker.

## Data

All tables are stored as `parquet` files with a `timestamp` column of type `int64` — **microseconds since UNIX epoch (UTC)**. This is the only time axis that should be used.

The universe is `perp:btcusdt` and `perp:ethusdt` and the same universe will be used on the hidden test.

Files and columns:

| path | columns |
|---|---|
| `data/binance_trades/perp_<sym>.parquet` | `timestamp, ticker, side, price, amount` |
| `data/binance_booktickers/perp_<sym>.parquet` | `timestamp, ticker, bid_price, bid_amount, ask_price, ask_amount` |
| `data/binance_liquidations/perp_<sym>.parquet` | `timestamp, ticker, side, price, amount` |
| `data/bybit_liquidations/<sym>.parquet` | `timestamp, ticker, side, price, amount` |

`ticker` is equal to `perp:btcusdt` / `perp:ethusdt` for Binance and `btcusdt` / `ethusdt` for Bybit. In both cases it matches the file name.

`side` convention:

- in `trades`, it is the **taker side** (`buy` means the taker bought, so the maker sold)
- in `liquidations`, it is the **liquidation order side** (`buy` means a short is force-closed by buying, which implies upward pressure)

## Cross-exchange delay

Bybit and Binance are different exchanges, so there is network latency between them. We assume that Bybit events become available to us no earlier than **200 ms** after their `timestamp`.

When building any features, Bybit liquidation timestamps must be shifted forward by `+200 ms` before aligning them to Binance trade time.

---

## Markout

Fix 3 horizons:

`τ ∈ {30s, 120s, 300s}`

For trade `i`:

- `p_i` is the trade price
- `m_i(τ)` is the Binance BBO mid at time `t_i + τ`, using **forward-fill** (the last observed mid available at time `t_i + τ`)
- if `t_i + τ` falls outside the available BBO range, the trade is excluded from the calculation
- `s_i = +1` if taker `buy`, which means maker `sell`
- `s_i = -1` if taker `sell`, which means maker `buy`
- `w_i = min(notional_i, 100_000)`

Maker PnL in bps:

```text
pnl_i(τ) = -s_i * (m_i(τ) - p_i) / p_i * 10_000 + 0.5
```

where `+0.5 bps` is the maker rebate.

---

## Signal

The signal defines a binary filter:

```text
f_i(τ) = 1, if the trade is filtered out
f_i(τ) = 0, if the trade is kept
```

---

## Score

Baseline:

```text
PnL_all(τ) =
    sum_i w_i * pnl_i(τ) / sum_i w_i
```

PnL on kept trades:

```text
PnL_kept(τ) =
    sum_i (1 - f_i(τ)) * w_i * pnl_i(τ)
    /
    sum_i (1 - f_i(τ)) * w_i
```

Final score:

```text
Score(τ) = PnL_kept(τ) - PnL_all(τ)
```

The higher `Score(τ)` is, the better.

You should also report PnL on filtered trades:

```text
PnL_filtered(τ) =
    sum_i f_i(τ) * w_i * pnl_i(τ)
    /
    sum_i f_i(τ) * w_i
```

---

## Constraint

The average daily clipped turnover of kept trades must be at least:

```text
500,000 USD per day
```

That is:

```text
KeptTurnoverPerDay =
    sum_i (1 - f_i(τ)) * w_i / number_of_days
    >= 500_000
```

---

## Split

- train: `2025-12-01 → 2026-01-31` (2 months)
- validation: `2026-02-01 → 2026-02-28` (1 month)
- the final test set will be hidden and unavailable

On the hidden test, both `Score(τ)` and the turnover constraint will be checked.

---

## Submission format

The solution should be a Python function that takes four data frames:

- `trades`
- `bbo`
- `liq_binance`
- `liq_bybit`

Each input has the same schema and columns as in the public files.

The function must return, for each `τ ∈ {30, 120, 300}`, an array of the same length as `trades`, containing:

- `0` to keep the trade
- `1` to filter the trade out

On the hidden test, the function will be called on the same 4 data types, but for different dates.

---

## ML

The filter `f_i(τ)` may be built using an ML model. For example, it can be framed as a classification task with weighted samples.
