"""Honest ZIP-area aggregation of NYC dog-related datasets.

Raw extracts are grouped or facility-level, never person-level. The `dog_runs`
column counts facilities tagged with each ZIP, including facilities tagged
with *multiple* ZIP codes. Do NOT sum dog runs across ZIPs to estimate the
number of distinct dog-run facilities.
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

SOURCE_NAMES = ("dog_runs", "dog_licenses", "dog_311", "dog_bites")
COLUMNS = ("zip_code", "dog_runs", "license_periods", "dog_related_311", "reported_bites", "documented_breeds")


def normalize_zip(raw: object) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if re.fullmatch(r"\d{5}\.0", value):
        value = value[:5]
    return value if re.fullmatch(r"\d{5}", value) and value != "00000" else None


def parse_zip_tags(raw: object) -> list[str]:
    """Return distinct ZIP tags from a facility's multi-ZIP field."""
    if raw is None:
        return []
    return list(dict.fromkeys(z for z in re.findall(r"(?<!\d)\d{5}(?!\d)", str(raw)) if z != "00000"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def zip_summary(raw_dir: Path, *, statuses: dict | None = None) -> tuple[list[dict], dict]:
    """Aggregate available grouped data; represent unavailable source metrics as blank.

    `statuses` comes from provenance and can mark a stale CSV as failed. Missing
    data must never become a numerical zero. An observed lack of reports *within*
    an otherwise complete source is represented by zero.
    """
    paths = {key: raw_dir / f"{key}.csv" for key in SOURCE_NAMES}
    available = [key for key, path in paths.items() if path.is_file() and
                 (statuses is None or statuses.get(key, {}).get("status") == "ok")]
    out = defaultdict(lambda: {"dog_runs": 0, "license_periods": 0,
                              "dog_related_311": 0, "reported_bites": 0,
                              "license_breeds": set()})
    invalid = defaultdict(int)
    multi_zip_count = 0
    for source in available:
        for row in read_csv(paths[source]):
            if source == "dog_runs":
                zips = parse_zip_tags(row.get("zipcode"))
                if len(zips) > 1:
                    multi_zip_count += 1
            else:
                code = normalize_zip(row.get("incident_zip") if source == "dog_311" else row.get("zipcode"))
                zips = [code] if code else []
            if not zips:
                invalid[source] += 1
                continue
            for code in zips:
                item = out[code]
                if source == "dog_runs":
                    item["dog_runs"] += 1
                elif source == "dog_licenses":
                    item["license_periods"] += int(row["license_periods"])
                    if row.get("breedname", "").strip():
                        item["license_breeds"].add(row["breedname"].strip())
                elif source == "dog_311":
                    item["dog_related_311"] += int(row["reports"])
                else:
                    item["reported_bites"] += int(row["bite_reports"])
    mapping = {"dog_runs": "dog_runs", "dog_licenses": "license_periods",
               "dog_311": "dog_related_311", "dog_bites": "reported_bites"}
    records = []
    for code, values in sorted(out.items()):
        record = {"zip_code": code}
        for src, column in mapping.items():
            record[column] = values[column] if src in available else ""
        record["documented_breeds"] = (len(values["license_breeds"]) if "dog_licenses" in available else "")
        records.append(record)
    return records, {"available_sources": available, "invalid_zip_rows": dict(invalid),
                     "multi_zip_facility_records": multi_zip_count,
                     "distinct_dog_run_facility_records": len(read_csv(paths["dog_runs"])) if "dog_runs" in available else None}


def make_summary_report(root: Path, notes: dict | None = None) -> Path:
    log_path = root / "data/metadata/query_log.json"
    statuses = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else None
    data, stats = zip_summary(root / "data/raw", statuses=statuses)
    target = root / "data/processed/zip_summary.csv"
    write_csv(target, data, list(COLUMNS))
    report = {
        "report_type": "data_inventory_not_a_safety_ranking",
        "zip_count": len(data), **stats,
        "limitations": [
            "ZIP-code areas are not neighborhood boundaries and do not measure walkable access or travel distance.",
            "Some dog-run facilities are tagged with more than one ZIP; sum over ZIPs double-counts these facilities.",
            "License periods are not unique dogs; the license extract is 2026 while reported incidents are from 2025.",
            "Dog-run data includes fenced facilities but does not include all permitted off-leash park areas.",
            "The 2025 311 extract includes only the descriptor Noise, Barking Dog (NR5), not all dog-related complaints.",
            "Complaint volume is affected by reporting behavior and may include multiple requests for one issue.",
            "Reported bite counts can be incomplete; owner ZIP in licensing is not the same as the incident ZIP.",
            "Counts are descriptive, not risk rates or measures of causality, safety, or best places to live.",
            "A zero reflects no observed matching records in the snapshot, not verified absence in the real world.",
            "Different sources have different time windows; inspect data/metadata/query_log.json.",
        ],
        "metadata": notes or {}
    }
    path = root / "data/processed/data_quality_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return target
