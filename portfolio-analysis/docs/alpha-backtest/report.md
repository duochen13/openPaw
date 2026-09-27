# Alpha model walk-forward backtest (issue #33)

Generated 2026-09-27T01:28:49+00:00 (UTC) by `scripts/backtest_alpha_signals.py --report-dir`.

## Method

- Walk-forward over the full price history of every ticker in `config/portfolio.yaml` (NOW, CRM, META, GOOGL, NVDA, ORCL, TSLA) vs QQQ, strictly no look-ahead: alpha, slope, t-statistic, and R² are all trailing-only; forward excess starts at t+1.
- Flip trigger (issue #32): slope neg→pos crossing, acceleration > 0, 3-session persistence, rolling-R² ≥ 0.5 noise gate; the gated variant adds the issue-#49 t-statistic credibility gate.
- **Hit** = forward excess vs QQQ > 0 over the horizon; **false alarm** = forward excess ≤ 0.
- **Realized move**: cumulative forward excess first reaches +3% within 120 sessions. **Lead time** = sessions from the signal to that first touch. Signals that never touch it are *unrealized*, not misses.
- **Regimes** (causal, labeled at the signal date from the trailing 250-session QQQ total return): bull ≥ +10%, bear ≤ -10%, else sideways.
- Counts are signal *occurrences*, not independent bets: consecutive signals have overlapping forward windows. Small-n cells are noise - treat them as descriptive, not predictive.

## Data and caching

- Price source: `data/prices.sqlite`, populated by `portfolio-analysis ingest-prices` (Yahoo Finance chart API, adjusted closes). The database is gitignored and NOT committed; this report reproduces from a fresh ingest.
- The shared DB covered only NOW/META/GOOGL/TSLA (+QQQ). CRM, NVDA, and ORCL were backfilled on 2026-09-26 via `ingest-prices CRM|NVDA|ORCL` (their industry benchmarks rode along). No EDGAR/fundamentals pulls: the backtest is price-only by design, kept that way to hold runtime near two minutes.
- Coverage per ticker:

| ticker | first bar | last bar | bars |
|---|---|---|---|
| NOW | 2020-09-24 | 2026-09-24 | 1507 |
| CRM | 2020-09-28 | 2026-09-25 | 1506 |
| META | 2020-09-24 | 2026-09-24 | 1507 |
| GOOGL | 2020-09-24 | 2026-09-24 | 1507 |
| NVDA | 2020-09-28 | 2026-09-25 | 1506 |
| ORCL | 2020-09-28 | 2026-09-25 | 1506 |
| TSLA | 2020-09-24 | 2026-09-24 | 1507 |
| QQQ | 2020-09-24 | 2026-09-25 | 1508 |

## Headline: flip trigger hit / false-alarm rates

### fixed time weight

| config | horizon | n | hit rate | mean excess | median excess | realized ≤120d | median lead (sessions) |
|---|---|---|---|---|---|---|---|
| `min_t=1.0|min_r2=0.3|p=3` | 20 | 53 | 52.8% | +1.20% | +0.76% | 94.3% | 12 |
| `min_t=1.0|min_r2=0.3|p=3` | 60 | 53 | 54.7% | +3.36% | +1.01% | 94.3% | 12 |
| `min_t=1.0|min_r2=0.3|p=3` | 120 | 52 | 51.9% | +7.02% | +1.08% | 94.3% | 12 |
| `min_t=1.0|min_r2=0.5|p=3` | 20 | 23 | 56.5% | +1.59% | +2.14% | 91.3% | 12 |
| `min_t=1.0|min_r2=0.5|p=3` | 60 | 23 | 47.8% | -0.48% | -0.22% | 91.3% | 12 |
| `min_t=1.0|min_r2=0.5|p=3` | 120 | 23 | 39.1% | +2.54% | -7.69% | 91.3% | 12 |
| `min_t=1.0|min_r2=0.7|p=3` | 20 | 5 | 80.0% | +5.76% | +4.56% | 100.0% | 8 |
| `min_t=1.0|min_r2=0.7|p=3` | 60 | 5 | 80.0% | +12.59% | +18.41% | 100.0% | 8 |
| `min_t=1.0|min_r2=0.7|p=3` | 120 | 5 | 80.0% | +40.87% | +46.52% | 100.0% | 8 |
| `min_t=1.5|min_r2=0.3|p=3` | 20 | 29 | 58.6% | +1.54% | +1.06% | 96.6% | 6 |
| `min_t=1.5|min_r2=0.3|p=3` | 60 | 29 | 51.7% | +4.10% | +0.76% | 96.6% | 6 |
| `min_t=1.5|min_r2=0.3|p=3` | 120 | 28 | 53.6% | +6.37% | +1.11% | 96.6% | 6 |
| `min_t=1.5|min_r2=0.5|p=3` | 20 | 15 | 53.3% | -0.38% | +0.76% | 93.3% | 6 |
| `min_t=1.5|min_r2=0.5|p=3` | 60 | 15 | 46.7% | -0.79% | -5.85% | 93.3% | 6 |
| `min_t=1.5|min_r2=0.5|p=3` | 120 | 15 | 40.0% | -3.57% | -7.69% | 93.3% | 6 |
| `min_t=1.5|min_r2=0.7|p=3` | 20 | 2 | 100.0% | +6.36% | +6.36% | 100.0% | 10 |
| `min_t=1.5|min_r2=0.7|p=3` | 60 | 2 | 100.0% | +26.20% | +26.20% | 100.0% | 10 |
| `min_t=1.5|min_r2=0.7|p=3` | 120 | 2 | 50.0% | +19.98% | +19.98% | 100.0% | 10 |
| `min_t=2.0|min_r2=0.3|p=3` | 20 | 5 | 60.0% | -0.10% | +0.23% | 100.0% | 3 |
| `min_t=2.0|min_r2=0.3|p=3` | 60 | 5 | 40.0% | -3.16% | -3.88% | 100.0% | 3 |
| `min_t=2.0|min_r2=0.3|p=3` | 120 | 4 | 50.0% | +4.37% | +2.70% | 100.0% | 3 |
| `min_t=2.0|min_r2=0.5|p=3` | 20 | 2 | 50.0% | -1.19% | -1.19% | 100.0% | 3 |
| `min_t=2.0|min_r2=0.5|p=3` | 60 | 2 | 50.0% | -2.13% | -2.13% | 100.0% | 3 |
| `min_t=2.0|min_r2=0.5|p=3` | 120 | 2 | 50.0% | +6.04% | +6.04% | 100.0% | 3 |
| `min_t=2.0|min_r2=0.7|p=3` | 20 | 0 | n/a | n/a | n/a | n/a | n/a |
| `min_t=2.0|min_r2=0.7|p=3` | 60 | 0 | n/a | n/a | n/a | n/a | n/a |
| `min_t=2.0|min_r2=0.7|p=3` | 120 | 0 | n/a | n/a | n/a | n/a | n/a |
| `min_t=None|min_r2=0.3|p=3` | 20 | 172 | 44.8% | +0.16% | -0.71% | 85.1% | 11 |
| `min_t=None|min_r2=0.3|p=3` | 60 | 170 | 49.4% | +1.53% | -0.17% | 85.1% | 11 |
| `min_t=None|min_r2=0.3|p=3` | 120 | 165 | 55.2% | +5.41% | +1.52% | 85.1% | 11 |
| `min_t=None|min_r2=0.5|p=2` | 20 | 96 | 49.0% | +0.04% | -0.12% | 88.5% | 10 |
| `min_t=None|min_r2=0.5|p=2` | 60 | 96 | 49.0% | +1.59% | -0.33% | 88.5% | 10 |
| `min_t=None|min_r2=0.5|p=2` | 120 | 95 | 51.6% | +6.94% | +0.82% | 88.5% | 10 |
| `min_t=None|min_r2=0.5|p=3` | 20 | 86 | 44.2% | -0.11% | -1.06% | 89.5% | 11 |
| `min_t=None|min_r2=0.5|p=3` | 60 | 86 | 50.0% | +1.35% | -0.07% | 89.5% | 11 |
| `min_t=None|min_r2=0.5|p=3` | 120 | 85 | 54.1% | +6.47% | +0.87% | 89.5% | 11 |
| `min_t=None|min_r2=0.5|p=5` | 20 | 68 | 42.6% | -0.01% | -1.39% | 85.3% | 12 |
| `min_t=None|min_r2=0.5|p=5` | 60 | 68 | 51.5% | +2.90% | +0.24% | 85.3% | 12 |
| `min_t=None|min_r2=0.5|p=5` | 120 | 68 | 57.4% | +8.88% | +2.70% | 85.3% | 12 |
| `min_t=None|min_r2=0.7|p=3` | 20 | 15 | 40.0% | -0.21% | -2.58% | 93.3% | 10 |
| `min_t=None|min_r2=0.7|p=3` | 60 | 15 | 53.3% | +5.43% | +0.76% | 93.3% | 10 |
| `min_t=None|min_r2=0.7|p=3` | 120 | 15 | 53.3% | +26.34% | +5.36% | 93.3% | 10 |

### enable time weight

| config | horizon | n | hit rate | mean excess | median excess | realized ≤120d | median lead (sessions) |
|---|---|---|---|---|---|---|---|
| `min_t=1.0|min_r2=0.3|p=3` | 20 | 58 | 43.1% | -0.06% | -1.29% | 79.3% | 10 |
| `min_t=1.0|min_r2=0.3|p=3` | 60 | 58 | 48.3% | +1.24% | -0.54% | 79.3% | 10 |
| `min_t=1.0|min_r2=0.3|p=3` | 120 | 56 | 50.0% | +4.64% | +0.02% | 79.3% | 10 |
| `min_t=1.0|min_r2=0.5|p=3` | 20 | 23 | 39.1% | +1.43% | -1.81% | 78.3% | 8 |
| `min_t=1.0|min_r2=0.5|p=3` | 60 | 23 | 43.5% | +4.14% | -0.66% | 78.3% | 8 |
| `min_t=1.0|min_r2=0.5|p=3` | 120 | 23 | 47.8% | +13.21% | -6.24% | 78.3% | 8 |
| `min_t=1.0|min_r2=0.7|p=3` | 20 | 5 | 20.0% | -5.34% | -10.52% | 60.0% | 3 |
| `min_t=1.0|min_r2=0.7|p=3` | 60 | 5 | 20.0% | -2.52% | -10.13% | 60.0% | 3 |
| `min_t=1.0|min_r2=0.7|p=3` | 120 | 5 | 20.0% | +6.04% | -16.36% | 60.0% | 3 |
| `min_t=1.5|min_r2=0.3|p=3` | 20 | 24 | 41.7% | -1.32% | -1.80% | 79.2% | 10 |
| `min_t=1.5|min_r2=0.3|p=3` | 60 | 24 | 45.8% | -1.28% | -2.16% | 79.2% | 10 |
| `min_t=1.5|min_r2=0.3|p=3` | 120 | 23 | 56.5% | +3.83% | +1.00% | 79.2% | 10 |
| `min_t=1.5|min_r2=0.5|p=3` | 20 | 10 | 40.0% | +0.74% | -1.80% | 80.0% | 12 |
| `min_t=1.5|min_r2=0.5|p=3` | 60 | 10 | 50.0% | -0.68% | +0.02% | 80.0% | 12 |
| `min_t=1.5|min_r2=0.5|p=3` | 120 | 10 | 60.0% | +10.32% | +0.87% | 80.0% | 12 |
| `min_t=1.5|min_r2=0.7|p=3` | 20 | 3 | 33.3% | -4.37% | -3.09% | 66.7% | 15 |
| `min_t=1.5|min_r2=0.7|p=3` | 60 | 3 | 33.3% | -1.55% | -18.95% | 66.7% | 15 |
| `min_t=1.5|min_r2=0.7|p=3` | 120 | 3 | 33.3% | +16.63% | -24.80% | 66.7% | 15 |
| `min_t=2.0|min_r2=0.3|p=3` | 20 | 10 | 50.0% | +3.49% | +1.78% | 80.0% | 8 |
| `min_t=2.0|min_r2=0.3|p=3` | 60 | 10 | 60.0% | +5.22% | +4.92% | 80.0% | 8 |
| `min_t=2.0|min_r2=0.3|p=3` | 120 | 10 | 60.0% | +13.59% | +6.42% | 80.0% | 8 |
| `min_t=2.0|min_r2=0.5|p=3` | 20 | 4 | 50.0% | +6.67% | +3.13% | 100.0% | 10 |
| `min_t=2.0|min_r2=0.5|p=3` | 60 | 4 | 75.0% | +12.34% | +16.08% | 100.0% | 10 |
| `min_t=2.0|min_r2=0.5|p=3` | 120 | 4 | 100.0% | +34.52% | +32.35% | 100.0% | 10 |
| `min_t=2.0|min_r2=0.7|p=3` | 20 | 1 | 100.0% | +8.04% | +8.04% | 100.0% | 6 |
| `min_t=2.0|min_r2=0.7|p=3` | 60 | 1 | 100.0% | +17.92% | +17.92% | 100.0% | 6 |
| `min_t=2.0|min_r2=0.7|p=3` | 120 | 1 | 100.0% | +72.86% | +72.86% | 100.0% | 6 |
| `min_t=None|min_r2=0.3|p=3` | 20 | 188 | 52.1% | +0.78% | +0.29% | 79.4% | 8 |
| `min_t=None|min_r2=0.3|p=3` | 60 | 185 | 50.8% | +2.09% | +0.11% | 79.4% | 8 |
| `min_t=None|min_r2=0.3|p=3` | 120 | 181 | 54.7% | +5.20% | +2.55% | 79.4% | 8 |
| `min_t=None|min_r2=0.5|p=2` | 20 | 92 | 43.5% | +0.46% | -0.54% | 85.9% | 9 |
| `min_t=None|min_r2=0.5|p=2` | 60 | 92 | 44.6% | +2.17% | -0.81% | 85.9% | 9 |
| `min_t=None|min_r2=0.5|p=2` | 120 | 92 | 55.4% | +9.62% | +1.10% | 85.9% | 9 |
| `min_t=None|min_r2=0.5|p=3` | 20 | 88 | 46.6% | +0.60% | -0.37% | 83.0% | 8 |
| `min_t=None|min_r2=0.5|p=3` | 60 | 88 | 45.5% | +1.78% | -1.45% | 83.0% | 8 |
| `min_t=None|min_r2=0.5|p=3` | 120 | 88 | 54.5% | +8.88% | +1.79% | 83.0% | 8 |
| `min_t=None|min_r2=0.5|p=5` | 20 | 79 | 45.6% | +0.35% | -0.43% | 88.6% | 10 |
| `min_t=None|min_r2=0.5|p=5` | 60 | 79 | 41.8% | +1.55% | -1.46% | 88.6% | 10 |
| `min_t=None|min_r2=0.5|p=5` | 120 | 79 | 54.4% | +9.29% | +1.75% | 88.6% | 10 |
| `min_t=None|min_r2=0.7|p=3` | 20 | 20 | 45.0% | +0.00% | -0.83% | 85.0% | 10 |
| `min_t=None|min_r2=0.7|p=3` | 60 | 20 | 30.0% | -0.66% | -4.34% | 85.0% | 10 |
| `min_t=None|min_r2=0.7|p=3` | 120 | 20 | 30.0% | +2.60% | -11.40% | 85.0% | 10 |

## Gated vs ungated (issue #49 design question)

Ungated = issue #32 as shipped (R² gate only). Gated rows add the t-statistic credibility gate.

### fixed time weight: threshold grid @60d horizon, persistence 3

| min_t | min_R² | n | hit rate | mean | median | realized ≤120d | median lead |
|---|---|---|---|---|---|---|---|
| ungated | 0.3 | 170 | 49.4% | +1.53% | -0.17% | 85.1% | 11 |
| ungated | 0.5 | 86 | 50.0% | +1.35% | -0.07% | 89.5% | 11 |
| ungated | 0.7 | 15 | 53.3% | +5.43% | +0.76% | 93.3% | 10 |
| 1 | 0.3 | 53 | 54.7% | +3.36% | +1.01% | 94.3% | 12 |
| 1 | 0.5 | 23 | 47.8% | -0.48% | -0.22% | 91.3% | 12 |
| 1 | 0.7 | 5 | 80.0% | +12.59% | +18.41% | 100.0% | 8 |
| 1.5 | 0.3 | 29 | 51.7% | +4.10% | +0.76% | 96.6% | 6 |
| 1.5 | 0.5 | 15 | 46.7% | -0.79% | -5.85% | 93.3% | 6 |
| 1.5 | 0.7 | 2 | 100.0% | +26.20% | +26.20% | 100.0% | 10 |
| 2 | 0.3 | 5 | 40.0% | -3.16% | -3.88% | 100.0% | 3 |
| 2 | 0.5 | 2 | 50.0% | -2.13% | -2.13% | 100.0% | 3 |
| 2 | 0.7 | 0 | n/a | n/a | n/a | n/a | n/a |

### fixed time weight: persistence sweep (ungated, R² ≥ 0.5) @60d

| persistence | n | hit rate | mean | median | realized ≤120d |
|---|---|---|---|---|---|
| 2 | 96 | 49.0% | +1.59% | -0.33% | 88.5% |
| 3 | 86 | 50.0% | +1.35% | -0.07% | 89.5% |
| 5 | 68 | 51.5% | +2.90% | +0.24% | 85.3% |

### enable time weight: threshold grid @60d horizon, persistence 3

| min_t | min_R² | n | hit rate | mean | median | realized ≤120d | median lead |
|---|---|---|---|---|---|---|---|
| ungated | 0.3 | 185 | 50.8% | +2.09% | +0.11% | 79.4% | 8 |
| ungated | 0.5 | 88 | 45.5% | +1.78% | -1.45% | 83.0% | 8 |
| ungated | 0.7 | 20 | 30.0% | -0.66% | -4.34% | 85.0% | 10 |
| 1 | 0.3 | 58 | 48.3% | +1.24% | -0.54% | 79.3% | 10 |
| 1 | 0.5 | 23 | 43.5% | +4.14% | -0.66% | 78.3% | 8 |
| 1 | 0.7 | 5 | 20.0% | -2.52% | -10.13% | 60.0% | 3 |
| 1.5 | 0.3 | 24 | 45.8% | -1.28% | -2.16% | 79.2% | 10 |
| 1.5 | 0.5 | 10 | 50.0% | -0.68% | +0.02% | 80.0% | 12 |
| 1.5 | 0.7 | 3 | 33.3% | -1.55% | -18.95% | 66.7% | 15 |
| 2 | 0.3 | 10 | 60.0% | +5.22% | +4.92% | 80.0% | 8 |
| 2 | 0.5 | 4 | 75.0% | +12.34% | +16.08% | 100.0% | 10 |
| 2 | 0.7 | 1 | 100.0% | +17.92% | +17.92% | 100.0% | 6 |

### enable time weight: persistence sweep (ungated, R² ≥ 0.5) @60d

| persistence | n | hit rate | mean | median | realized ≤120d |
|---|---|---|---|---|---|
| 2 | 92 | 44.6% | +2.17% | -0.81% | 85.9% |
| 3 | 88 | 45.5% | +1.78% | -1.45% | 83.0% |
| 5 | 79 | 41.8% | +1.55% | -1.46% | 88.6% |

## Per-stock flip results (enable time weight, @60d horizon)

| stock | gate | n | hit rate | mean | median | realized ≤120d | median lead |
|---|---|---|---|---|---|---|---|
| NOW | ungated | 14 | 42.9% | -2.72% | -3.32% | 78.6% | 12 |
| CRM | ungated | 9 | 22.2% | -7.91% | -12.23% | 55.6% | 7 |
| META | ungated | 13 | 53.8% | -0.59% | +0.52% | 76.9% | 6 |
| GOOGL | ungated | 19 | 36.8% | +0.26% | -3.01% | 84.2% | 21 |
| NVDA | ungated | 27 | 59.3% | +9.29% | +1.41% | 92.6% | 6 |
| ORCL | ungated | 1 | 100.0% | +52.57% | +52.57% | 100.0% | 16 |
| TSLA | ungated | 5 | 20.0% | -7.03% | -12.41% | 100.0% | 4 |
| NOW | t >= 1.5 | 0 | n/a | n/a | n/a | n/a | n/a |
| CRM | t >= 1.5 | 0 | n/a | n/a | n/a | n/a | n/a |
| META | t >= 1.5 | 0 | n/a | n/a | n/a | n/a | n/a |
| GOOGL | t >= 1.5 | 2 | 50.0% | +0.19% | +0.19% | 100.0% | 58 |
| NVDA | t >= 1.5 | 7 | 57.1% | +4.41% | +0.31% | 85.7% | 10 |
| ORCL | t >= 1.5 | 0 | n/a | n/a | n/a | n/a | n/a |
| TSLA | t >= 1.5 | 1 | 0.0% | -38.12% | -38.12% | 0.0% | n/a |

## Regime-segmented flip results (enable time weight, @60d horizon)

| regime | gate | n | hit rate | mean | median | realized ≤120d | median lead |
|---|---|---|---|---|---|---|---|
| bull | ungated | 35 | 45.7% | +1.62% | -0.55% | 80.0% | 12 |
| bear | ungated | 22 | 27.3% | -0.92% | -5.70% | 81.8% | 6 |
| sideways | ungated | 19 | 36.8% | -3.75% | -5.43% | 78.9% | 13 |
| None | ungated | 12 | 91.7% | +15.91% | +15.45% | 100.0% | 5 |
| bull | t >= 1.5 | 5 | 60.0% | +3.32% | +0.31% | 80.0% | 10 |
| bear | t >= 1.5 | 2 | 50.0% | -1.51% | -1.51% | 50.0% | 4 |
| sideways | t >= 1.5 | 1 | 0.0% | -20.80% | -20.80% | 100.0% | 26 |
| None | t >= 1.5 | 2 | 50.0% | +0.19% | +0.19% | 100.0% | 58 |

## Slope / alpha-cross signals (enable time weight, WLS slope)

The raw crossings the flip trigger is built on, scored the same way. Issue #39 removed acceleration as a product series; acceleration survives only as the flip trigger's confirmation step.

### alpha_cross (n=189 events)

| segment | n | hit rate @60d | mean @60d | median @60d | realized ≤120d | median lead |
|---|---|---|---|---|---|---|
| **all** | 175 | 47.4% | +0.55% | -1.03% | 84.1% | 9 |
| NOW | 38 | 50.0% | -0.88% | +0.03% | 89.7% | 16 |
| CRM | 20 | 45.0% | +2.99% | -1.32% | 86.4% | 8 |
| META | 15 | 53.3% | -0.40% | +4.53% | 61.1% | 4 |
| GOOGL | 16 | 43.8% | +1.40% | -1.17% | 94.7% | 8 |
| NVDA | 21 | 57.1% | +4.92% | +2.91% | 96.2% | 10 |
| ORCL | 34 | 55.9% | +5.07% | +2.44% | 88.2% | 18 |
| TSLA | 31 | 29.0% | -7.15% | -13.16% | 67.7% | 7 |
| *bull* | 102 | 46.1% | +0.70% | -1.46% | 82.8% | 8 |
| *bear* | 36 | 47.2% | -2.38% | -1.38% | 83.3% | 10 |
| *sideways* | 16 | 37.5% | +1.34% | -1.21% | 93.8% | 12 |

### slope_cross (n=258 events)

| segment | n | hit rate @60d | mean @60d | median @60d | realized ≤120d | median lead |
|---|---|---|---|---|---|---|
| **all** | 246 | 50.4% | +2.10% | +0.29% | 83.3% | 9 |
| NOW | 40 | 52.5% | +0.91% | +0.29% | 88.1% | 8 |
| CRM | 34 | 41.2% | -2.49% | -3.49% | 74.3% | 8 |
| META | 37 | 54.1% | -0.24% | +0.80% | 76.9% | 9 |
| GOOGL | 34 | 44.1% | +0.59% | -2.95% | 75.7% | 13 |
| NVDA | 31 | 58.1% | +11.17% | +6.12% | 93.9% | 5 |
| ORCL | 39 | 51.3% | +0.43% | +0.74% | 87.5% | 13 |
| TSLA | 31 | 51.6% | +6.13% | +1.97% | 87.5% | 8 |
| *bull* | 146 | 47.3% | -0.03% | -0.55% | 78.5% | 8 |
| *bear* | 38 | 42.1% | +3.58% | -2.58% | 89.5% | 9 |
| *sideways* | 28 | 53.6% | +2.02% | +1.56% | 92.9% | 9 |

## Threshold recommendations (feeds #32 and #49)

What the walk-forward says, in order of decision priority:

1. **Do not ship t ≥ 1.5 as the default alert gate (#49).** On enable time weight it collapses coverage 88 → 10 flips over six years while the @60d hit rate moves 45.5% → 50.0% - statistically indistinguishable at n=10. The gate does not buy accuracy; it buys an NVDA filter (7 of the 10 surviving flips are NVDA). t ≥ 1.0 keeps 23 flips at 43.5% - no gain either. Keep the issue-#49 tiered proposal instead: t ≥ 1.0 = watch, t ≥ 1.5 = qualified, t ≥ 2.0 = strong, and show the tier in the alert rather than suppressing sub-1.5 flips.

2. **Keep the R² noise gate at 0.5; do not tighten it.** On enable time weight, raising min_R² 0.5 → 0.7 cuts coverage 88 → 20 and the @60d hit rate *falls* 45.5% → 30.0%. The R² gate is not a monotone quality knob on the WLS fit - it discards the idiosyncratic moves where alpha actually lives. (On fixed-weight OLS it helps mildly, 50.0% → 53.3% at n=15, but that is a different model.)

3. **Persistence 3 is fine; the sweep is flat.** Ungated wls @60d: p=2 → 44.6%, p=3 → 45.5%, p=5 → 41.8%. No evidence for changing the shipped value.

4. **Suppress or down-weight flip alerts in bear regimes.** Ungated wls flips fired in bear markets hit 27.3% @60d (n=22) vs 45.7% in bull (n=35) and 36.8% sideways (n=19). A regime-aware alert ('flip + bull/sideways') would have avoided the worst segment. At minimum, surface the prevailing regime in the alert payload (#32).

5. **Calibrate per stock - the trigger is an NVDA signal.** NVDA: 27 flips, 59.3% hit, +9.29% mean @60d. CRM (22.2%, n=9) and TSLA (20.0%, n=5) are actively worse than coin flips; GOOGL 36.8%, NOW 42.9%, META 53.8%. Ship per-stock hit rates in the alert UI so a CRM flip is not presented with the same confidence as an NVDA flip, or restrict auto-alerts to names where the trigger has earned it.

6. **Reframe what the alert means: early-move detector, not 60-day hold signal.** Median lead time to the first +3% cumulative excess is 8 sessions and 83.0% of ungated flips touch +3% within 120d - but only 45.5% are still above zero at day 60. The trigger often catches the start of a move that fades. Evaluate future threshold changes on *realization within 20d*, not fixed-horizon hit rate, and word the alert as 'regime change watch - confirm within ~2 weeks'.

7. **Quote hit rates ex-2020-21.** Twelve ungated flips predate the regime window (Sep 2020 - Sep 2021, the COVID-recovery rally) and hit 91.7%. Excluding that block, the ungated wls @60d hit rate is 38.2% (n=76), not 45.5%. Any dashboard copy citing backtest accuracy should use the ex-recovery figure.

8. **The flip trigger's confirmation stack does not beat raw slope_cross.** Ungated wls flips: 45.5% @60d (n=88); raw slope_cross on the same series: 50.4% (n=246) with +2.10% mean. Acceleration + persistence + R² buy a smaller, no-more-accurate alert set. If #32 wants fewer, better alerts, the per-stock and regime filters above are the levers with evidence - not stricter t or R².

Open for Daniel: (a) accept the tiered t display vs a hard gate; (b) whether bear-regime suppression is acceptable for a 'watch' product (it trades recall for precision); (c) whether to run the min_alpha economic-size guard sweep (left at None here) before #49 is finalized.

## Caveats and limitations

- Overlapping forward windows: consecutive signals share most of their 60/120d window, so n overstates the number of independent bets; treat hit rates as descriptive.
- Small samples: the gated configs fire 10-15 times in six years. Any threshold comparison at that n is suggestive, not conclusive.
- Survivorship/look-ahead: none in the signal path (trailing-only), but the universe is today's portfolio - names that would have been dropped historically are absent by construction.
- Price-only: no fundamentals conditioning (TTM P/E, KPIs) - a deliberate scope cut for runtime; EDGAR pulls are quarterly while the trigger is daily.
- Regime labels use the benchmark's trailing 250d return - a reasonable but arbitrary cut (±10%); results are robust to the exact cut only insofar as the tables show.
- These are regime-change signals for validation, not buy signals.

## Reproduce

```bash
cd portfolio-analysis
# one-time: populate the (gitignored) price cache, incl. the three
# names missing from older snapshots:
python3 -m portfolio_analysis.cli ingest-prices          # whole universe
# or: python3 -m portfolio_analysis.cli ingest-prices CRM  # single name

# full backtest + this report (console tables + docs/alpha-backtest/):
python3 scripts/backtest_alpha_signals.py --report-dir docs/alpha-backtest
```

Runtime is dominated by the rolling WLS regressions (~2 min on this machine); the threshold grid reuses the rolling series, so each grid cell costs one cheap trigger scan.
