"""Download grouped, non-person-level NYC Open Data snapshots.

The 311 source is queried one month at a time so a full-year SoQL request does
not time out. Source query URLs and coverage are saved to the provenance log.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pawcity.pipeline import make_summary_report, write_csv  # noqa: E402

BASE = "https://data.cityofnewyork.us/resource"
DATASETS = {"dog_runs": "hxx3-bwgv", "dog_licenses": "nu7n-tubp",
            "dog_311": "erm2-nwe9", "dog_bites": "rsgh-akpg"}
BARKING_DESCRIPTOR = "Noise, Barking Dog (NR5)"


def request(dataset: str, params: dict, timeout: int = 90):
    url = f"{BASE}/{DATASETS[dataset]}.json?{urlencode(params)}"
    headers = {"User-Agent": "PawCity-Academic-Research/1.0", "Accept": "application/json"}
    if os.getenv("SOCRATA_APP_TOKEN"):
        headers["X-App-Token"] = os.environ["SOCRATA_APP_TOKEN"]
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=headers), timeout=timeout) as response:
                records = json.loads(response.read().decode("utf-8"))
            if not isinstance(records, list):
                raise ValueError("Expected a JSON array from Socrata API")
            if len(records) >= int(params.get("$limit", 1000)):
                raise RuntimeError("Query reached its row limit; refusing silent truncation")
            return records, url
        except HTTPError as err:
            detail = err.read(400).decode("utf-8", "replace")
            if err.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise RuntimeError(f"Socrata returned HTTP {err.code}: {detail}") from err
        except (URLError, TimeoutError) as err:
            if attempt == 2:
                raise RuntimeError(f"Socrata request failed: {err}") from err
        time.sleep(2 * (attempt + 1))
    raise RuntimeError("Request failed after retries")


def fetch(dataset: str, year: int, timeout: int):
    now = datetime.now(timezone.utc).isoformat()
    meta = {"dataset_id": DATASETS[dataset], "status": "ok", "retrieved_at_utc": now,
            "source_url": f"https://data.cityofnewyork.us/d/{DATASETS[dataset]}"}
    if dataset == "dog_runs":
        fields = ["objectid", "name", "zipcode", "borough", "dog_area_type", "seating", "surface", "communityboard"]
        rows, url = request(dataset, {"$select": ",".join(fields), "$limit": 5000}, timeout)
        meta["api_query_url"] = url
    elif dataset == "dog_licenses":
        yrs, url_yrs = request(dataset, {"$select": "extract_year,count(*) as records",
                                         "$group": "extract_year", "$order": "extract_year DESC", "$limit": 100}, timeout)
        available_years = sorted((str(x.get("extract_year", "")) for x in yrs if x.get("extract_year")), reverse=True)
        if not available_years:
            raise RuntimeError("No licensing extract year available")
        extract = available_years[0]
        fields = ["zipcode", "breedname", "license_periods"]
        rows, url = request(dataset, {"$select": "zipcode,breedname,count(*) as license_periods",
                                     "$where": f"extract_year='{extract}' and zipcode is not null",
                                     "$group": "zipcode,breedname", "$limit": 50000}, timeout)
        meta.update({"api_query_url": url, "license_years_query_url": url_yrs, "license_extract_year": extract})
    elif dataset == "dog_bites":
        fields = ["zipcode", "bite_reports"]
        rows, url = request(dataset, {"$select": "zipcode,count(*) as bite_reports",
                                     "$where": f"dateofbite >= '{year}-01-01T00:00:00' and "
                                               f"dateofbite < '{year+1}-01-01T00:00:00' and zipcode is not null",
                                     "$group": "zipcode", "$limit": 50000}, timeout)
        meta.update({"api_query_url": url, "event_year": year})
    elif dataset == "dog_311":
        fields = ["incident_zip", "complaint_type", "descriptor", "reports"]
        by_zip = Counter()
        monthly = {}
        query_urls = []
        for month in range(1, 13):
            start = f"{year}-{month:02d}-01T00:00:00"
            end = f"{year+1}-01-01T00:00:00" if month == 12 else f"{year}-{month+1:02d}-01T00:00:00"
            rows_month, url = request(dataset, {"$select": "incident_zip,count(*) as reports",
                                                "$where": f"created_date >= '{start}' AND created_date < '{end}' "
                                                          f"AND descriptor = '{BARKING_DESCRIPTOR}' AND incident_zip IS NOT NULL",
                                                "$group": "incident_zip", "$limit": 1000}, timeout)
            query_urls.append(url)
            monthly[str(month)] = sum(int(r["reports"]) for r in rows_month)
            for r in rows_month:
                by_zip[str(r["incident_zip"])] += int(r["reports"])
            print(f"  Month {month:02d}: {monthly[str(month)]} requests", flush=True)
        rows = [{"incident_zip": z, "complaint_type": "Noise", "descriptor": BARKING_DESCRIPTOR,
                 "reports": total} for z, total in sorted(by_zip.items())]
        meta.update({"event_year": year, "complaint_scope": f"Only descriptor = '{BARKING_DESCRIPTOR}', NOT all dog complaints",
                     "api_query_urls": query_urls, "monthly_counts": monthly})
    else:
        raise ValueError("Unknown dataset")
    normalized = [{field: r.get(field, "") for field in fields} for r in rows]
    meta["rows"] = len(normalized)
    return normalized, fields, meta


def main() -> int:
    parser = argparse.ArgumentParser(description="Download official aggregated NYC dog-related datasets")
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--only", choices=DATASETS)
    options.add_argument("--all", action="store_true")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    if args.year != 2025:
        parser.error("This research snapshot currently expects the full calendar year 2025")
    log_path = ROOT / "data/metadata/query_log.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    selected = DATASETS.keys() if args.all else [args.only]
    failures = []
    for dataset in selected:
        print(f"Fetching {dataset}...", flush=True)
        try:
            rows, fields, metadata = fetch(dataset, args.year, args.timeout)
            write_csv(ROOT / "data/raw" / f"{dataset}.csv", rows, fields)
            log[dataset] = metadata
            print(f"  Saved {len(rows)} grouped/facility records", flush=True)
        except Exception as err:
            failures.append(dataset)
            log[dataset] = {"status": "error", "error": str(err), "time_utc": datetime.now(timezone.utc).isoformat()}
            print(f"  FAILED: {err}", file=sys.stderr)
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    make_summary_report(ROOT)
    print("Saved data/metadata/query_log.json and data/processed/zip_summary.csv")
    if failures:
        print(f"Incomplete sources: {', '.join(failures)}; missing metrics are not zeros", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
