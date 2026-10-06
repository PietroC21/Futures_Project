# ES 0DTE Stale Quotes

**When E-mini S&P 500 (ES) futures move, how long do 0DTE ES option quotes stay stale, and is that window large and long enough to profit from after costs?**

This is a measurement study built on CME Globex market data from [Databento](https://databento.com) (`GLBX.MDP3`). It is not a live trading system: we measure the size, duration and frequency of latency-arbitrage opportunities between ES futures and same-day-expiry ES options.

> Status: planning. Commands below describe the intended interface and will work once the tasks in the [Issues](../../issues) are complete.

---

## Motivation

Options market makers reprice their quotes after the underlying future moves. That repricing takes time, measured in microseconds. In that window, an option quote can sit at a price that is no longer fair given the new futures price, so a fast taker could trade against it.

CME timestamps every event with `ts_event`, the matching-engine time, at nanosecond resolution. That lets us measure this race directly from historical data.

**Hypothesis:** one ES tick is 0.25 index points. A 0.5-delta option should therefore move about 0.125 points, which is usually smaller than the option tick size plus fees. So we expect single-tick futures moves to **rarely** create profitable stale quotes, with real opportunities concentrated in **multi-tick jumps** such as sweeps and news.

## Research questions

1. **Reaction latency:** after a futures best bid/offer change, how long until near-the-money option quotes update? How does that vary by moneyness and time of day?
2. **Opportunity frequency:** what fraction of futures moves leave at least one option quote stale by more than costs?
3. **Window duration:** how long do those stale quotes survive?
4. **Resolution:** is a stale quote usually removed by the market maker (cancel) or hit by a taker (fill)? What is the markout of those fills?

## Method

| Step | What we do | Why |
|---|---|---|
| Data | ES front-month futures and 0DTE ES options, `mbp-1` (top of book) plus trades. Roughly 10 strikes around at-the-money, 3–5 trading days. | Stale quotes are defined at the top of book, so deeper levels add data volume without adding information. |
| Robustness data | `mbo` (full order book) for 1–2 recent days | Order-level actions let us separate a market maker pulling a quote (cancel) from a taker hitting it (fill). |
| Event | A change in the futures best bid/offer at time `t0`, using `ts_event` | `ts_event` is the exchange's clock. `ts_recv` adds network delay unrelated to market-maker reaction. |
| Fair value | Option mid before `t0` + Δ × ΔF, with Δ from Black-76 using the implied vol of the pre-move mid | At microsecond horizons, gamma and theta are negligible, so a delta adjustment captures the repricing. |
| Stale test | Option ask < fair − cost, or option bid > fair + cost | Cost = half the option tick + exchange fees. A quote is only an opportunity if it beats costs. |
| Validity check | Confirm that option reaction latencies are never systematically negative | Futures and options may run on different matching engines. Their clocks must be comparable for microsecond lead-lag to mean anything. |

## Outputs

- Distribution of option reaction latency (histogram and quantiles), split by moneyness and session time
- Opportunity rate and edge per futures move, split by move size in ticks
- Survival curve of stale windows
- Cancel vs. fill breakdown and post-fill markouts (`mbo` days)
- A short written report in `notebooks/results.ipynb`

## Repository layout

```
data/
  raw/            Databento downloads (not committed)
  processed/      cleaned parquet files (not committed)
scripts/
  download.py     pulls data from Databento and caches it
  run_study.py    runs the full pipeline and writes results
src/stale_quotes/
  config.py       dates, symbols, strike range, cost parameters
  loaders.py      reads cached data into aligned DataFrames
  instruments.py  picks 0DTE expiry and near-the-money strikes
  black76.py      option pricing, delta, implied vol
  events.py       detects futures best bid/offer changes
  staleness.py    fair value and stale-quote detection
  metrics.py      latency, frequency, duration, markouts
tests/            unit tests (pytest)
notebooks/        results only; all logic lives in src/
```

## How to run

**Requirements:** Python 3.11+ and a Databento API key with CME (`GLBX.MDP3`) access.

```bash
git clone <repo-url>
cd es-0dte-stale-quotes
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export DATABENTO_API_KEY=db-...    # Windows: set DATABENTO_API_KEY=db-...

python scripts/download.py         # caches data to data/raw/ (check cost first, see below)
python scripts/run_study.py        # writes figures and tables to results/
pytest                             # runs unit tests
```

**Data cost:** `download.py` prints the Databento cost estimate and asks for confirmation before downloading. Options data can be large; the default config keeps it to a small strike range and a few days.

**Dates:** full-depth (`mbo`) data under the course license only covers roughly the last 1–2 months. Default dates in `config.py` will be set inside that window.

## Scope limits

- One product (ES) and one expiry type (0DTE). We are not covering other CME markets.
- Measurement only: no live trading, no queue-position simulation.
- Fees are a flat per-contract assumption, documented in `config.py`.

## Team

| Member | Part 1 role |
|---|---|
| Pietro Candiani | Tech leader (repo owner) |
| Cesare Bavaresco | Communication leader |
| _TBD_ | Design leader |

## Contributing

1. Fork this repo and create a branch per issue (`issue-<number>-short-name`).
2. Open a pull request into `main` that references the issue (`Closes #<number>`).
3. At least one other team member reviews before merge.
4. New logic needs a unit test in `tests/`.
