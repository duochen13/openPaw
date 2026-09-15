# Event collection implementation notes

The historical Plan 2 sample code is superseded by the implementation under
`src/portfolio_analysis/`. Its source contracts are implemented as follows.

| Component | Contract and validation |
|---|---|
| Calendar | Observed benchmark sessions; inclusive `[-2,+1]` boundaries. The CLI defers a clamped/incomplete window. Tests cover weekends, Good Friday, and invalid window sizes. |
| HTTP | Credential-independent request hash points to content-addressed JSON; cache before adapter parsing. Every attempt reserves quota under a POSIX lock. Atomic writes; bounded retries; refusal persistence; 24-hour TTL for mutable indexes. Tests cover death, restart, retry exhaustion, corruption, key rotation, echoed keys, and rollover. |
| Evidence types | UTC document instants, `America/New_York` dates. Filing/earnings date-only fields remain calendar dates. Model-written narrative has no constructor into verified facts. |
| EDGAR | Bind CIK when constructing the source, conforming to the common `collect` signature. Merge recent and every submission archive, validate parallel columns, filter forms, and deduplicate accessions. |
| Earnings | `quarterlyEarnings`; absent dates ignored, missing numbers remain null, dates not timezone-shifted. EPS values carry unknown-vintage and non-causal caveats. |
| News | Query UTC bounds corresponding to inclusive Eastern dates; post-filter timestamps. Relevance comes from the requested ticker. Deduplicate article URLs; conflicting duplicate content fails. Saturated 1,000-item windows fail visibly rather than silently truncating. |
| HN | Search company name plus configured aliases, including historical names. Paginate and deduplicate. Fall back to `story_title` and HN URLs. Approximate vendor counts are surfaced as partial coverage, not treated as an empty answer. |
| Macro | Checked-in release dates with per-series coverage and source URLs. Out-of-coverage is unknown. Includes 2025 shutdown rescheduling and the December 23 PCE data update. |
| Bundle | `verified` is an array of `{key,value,source,detail}` so multiple facts retain provenance. Stable canonical hash sorts facts and documents; no fetch timestamps enter the hash. Coverage separates missing API keys, approximate HN totals, macro coverage, and thin news. |
| CLI | Supports ticker aliases and single-date runs. Reuse bundles only when collection inputs and content hashes match. A quota stop returns 0 with progress; malformed source data returns 1 without publishing an empty bundle. |

The checked-in tests use deliberately small provider-shaped fixtures for edge
cases, with separate live acceptance tests for the EDGAR 2022/2024 anchors,
HackerNews, and Alpha Vantage. They are not presented as recorded live responses.

## Lifecycle choices

A completed historical bundle is a durable snapshot. Use `--rebuild` to reparse
its cached sources; once mutable source cache entries are 24 hours old, this
also refreshes those entries. Historical news/HN caches are permanent. Raw
object versions remain available after mutable indexes refresh. A fresh cache
directory is the explicit way to request a new historical-source snapshot.

A provider refusal is persisted separately from counted attempts, so a refusal
does not pretend that 25 requests were observed locally. The local ledger uses
UTC days. If the provider's reset is later, its next refusal blocks that UTC day.
Other applications' Alpha Vantage usage cannot be counted by this local ledger.

“Completed” in progress means an artifact was written or reused for all enabled
sources. It does not mean source coverage is complete; missing credentials or
approximate search totals remain visible in each artifact.

No model calls, attribution prompt, controls, or production renderer were added.
Plan 3 remains dependent on live news/earnings bundles and Muse readiness.
