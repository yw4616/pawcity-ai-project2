# Data dictionary and provenance

All data files are **real NYC Open Data extracts supplied by the project author**. The snapshots were downloaded on November 10, 2026 (UTC timestamps in `data/metadata/query_log.json`). The aggregation never downloads personal owner information.

| Source | File | Primary fields | Grain / limits |
|---|---|---|---|
| NYC Parks Dog Runs (`hxx3-bwgv`) | `data/raw/dog_runs.csv` | `objectid`, `name`, `zipcode`, `borough`, `surface`, `seating` | 95 facility records; some have blank, invalid, or multiple ZIP tags |
| Dog Licensing (`nu7n-tubp`) | `data/raw/dog_licenses.csv` | `zipcode`, `breedname`, `license_periods` | 19,091 ZIP × breed **groups** for the 2026 extract; NOT 19,091 unique dogs |
| NYC 311 (`erm2-nwe9`) | `data/raw/dog_311.csv` | `incident_zip`, `reports`, `descriptor` | 180 ZIP aggregates representing 8,327 barking-noise requests in calendar year **2025**; not all dog complaints |
| Dog Bite Reports (`rsgh-akpg`) | `data/raw/dog_bites.csv` | `zipcode`, `bite_reports` | 241 ZIP groups for 2025 reports; not a population or risk denominator |

`data/processed/zip_summary.csv` is a descriptive join indexed by ZIP strings; it does not ensure all ZIPs are inside NYC. `PawCityResearch` uses a conservative NYC ZIP-code string scope for citywide exploration and explains this is not an official geographic boundary. For user-provided ZIPs, it reports what the snapshot actually contains. `dog_runs` is a **per-ZIP tagged-facility count**; one facility tagged with multiple ZIPs appears in more than one ZIP count, and ZIP-level counts must not be summed for the number of distinct facilities.

A zero denotes no matching observed records in a successfully downloaded and covered source. If a source is missing/failed, the summarizer writes blank fields and the live agent refuses the incomplete data instead of interpreting blanks as zero.

## What these data cannot establish

- Named neighborhood limits, exact walking routes, park capacity or off-leash access beyond fenced runs.
- Actual independent dog population, because dog licenses can be renewed and 2026 ownership records differ from the 2025 incident geography.
- Probability that a given dog will be bitten or that a ZIP is objectively safe. Reporting rates, exposure denominators and incident completeness are unknown.
- The number of unique barking incidents (multiple service requests might describe one issue).
- Causal relationships between dog ownership, parks, complaints and bites.

## Exact query evidence

See `data/metadata/query_log.json`: source IDs, query URL(s), retrieval timestamps, 2025 monthly 311 counts and 2026 licensing extract year. `scripts/download_data.py` can reproduce the queries, including 12 month-scoped 311 requests to avoid API timeouts. The dashboard links back to original official source pages.
