"""Generate real same-model, no-tools vs. PawCity comparison answers.

Results are checkpointed after EACH baseline and EACH completed agent answer.
If a rate limit or connection error interrupts a run, rerun the same command:
completed results and baseline answers are reused without duplicate API calls.

Requires Google Cloud ADC and GOOGLE_CLOUD_PROJECT. Run: uv run python scripts/compare_samples.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pawcity.research_agent import GeminiModel, PawCityResearch  # noqa: E402

SAMPLES = [
    {"id": "run_coverage", "question": "Which NYC ZIP codes have the most documented dog runs?",
     "source": "data/processed/zip_summary.csv; data/raw/dog_runs.csv", "expected": "10024 has five ZIP-tagged dog runs; 10040, 10471, and 11201 have three each. Note the snapshot lists 95 distinct facilities, some without valid ZIP tags."},
    {"id": "run_gap", "question": "Which NYC ZIP areas have no recorded dog runs despite many license periods?",
     "source": "data/processed/zip_summary.csv; data/raw/dog_licenses.csv", "expected": "Examples: 10025 (0 tagged dog runs, 2,175 license periods), 10023 (0, 1,957), 10128 (0, 1,597). This is not proof of inadequate walkable access."},
    {"id": "zip_compare", "question": "Compare ZIP 10001 and ZIP 10002 for dog runs, license periods, 2025 barking requests and bite reports.",
     "source": "data/processed/zip_summary.csv and all four source CSVs", "expected": "10001: 0 runs, 811 license periods, 45 barking requests, 15 bite reports. 10002: 2 runs, 1,070 license periods, 72 barking requests, 16 bite reports. Sources differ by geography and year."},
]


def write_checkpoint(model_name: str, records: list[dict]) -> Path:
    output = ROOT / "reports" / "sample_comparisons.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "model": model_name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "comparisons": records,
    }
    # Atomic replace avoids corrupting valid checkpoints if the kernel exits.
    tmp = output.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(output)
    return output


def load_checkpoint(model_name: str) -> list[dict]:
    output = ROOT / "reports" / "sample_comparisons.json"
    if not output.exists():
        return []
    data = json.loads(output.read_text(encoding="utf-8"))
    if data.get("model") != model_name:
        raise RuntimeError(
            "Existing comparison file uses a different model. "
            "Archive the GPT checkpoint before starting Gemini comparisons."
        )
    records = data.get("comparisons", [])
    if not isinstance(records, list):
        raise ValueError("Existing comparison checkpoint is invalid.")
    return records


def update_readme(records: list[dict]) -> None:
    """Update README only after all requested comparisons have finished."""
    if len(records) != len(SAMPLES) or any(
        "agent_answer" not in r or "same_model_no_system_no_tools_answer" not in r
        for r in records
    ):
        raise RuntimeError("All comparison results must be complete before updating README.")
    readme = ROOT / "README.md"
    marker_start = "<!-- COMPARISON_RESULTS_START -->"
    marker_end = "<!-- COMPARISON_RESULTS_END -->"
    original = readme.read_text(encoding="utf-8")
    if marker_start not in original or marker_end not in original:
        raise ValueError("README comparison markers were not found.")

    def fmt(value: str) -> str:
        return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")

    lines = [
        "| Question | Same model, no tools or system prompt | Tool-enabled PawCity agent |",
        "|---|---|---|",
    ]
    for item in SAMPLES:
        record = next(r for r in records if r["id"] == item["id"])
        lines.append(
            f"| {fmt(record['question'])} | "
            f"{fmt(record['same_model_no_system_no_tools_answer'])} | "
            f"{fmt(record['agent_answer'])} |"
        )
    start = original.index(marker_start) + len(marker_start)
    end = original.index(marker_end)
    updated = original[:start] + "\n" + "\n".join(lines) + "\n" + original[end:]
    readme.write_text(updated, encoding="utf-8")


def main() -> None:
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        raise SystemExit("Set GOOGLE_CLOUD_PROJECT and authenticate with Google Cloud ADC first.")
    model = GeminiModel()
    agent = PawCityResearch(ROOT, llm=model, max_turns=2)
    records = load_checkpoint(model.model)
    by_id = {item["id"]: item for item in records}
    for item in SAMPLES:
        sample_id = item["id"]
        record = by_id.get(sample_id)
        if record is not None:
            if record["question"] != item["question"]:
                raise ValueError(f"Question changed for {sample_id}; cannot reuse old response.")
            if record.get("agent_answer"):
                print("Already completed; skipping both calls:", sample_id, flush=True)
                continue
        else:
            record = dict(item)
            by_id[sample_id] = record

        if "same_model_no_system_no_tools_answer" not in record:
            print("Running same-model no-tools baseline:", sample_id, flush=True)
            record["same_model_no_system_no_tools_answer"] = model.request(
                item["question"], instructions=None
            )
            write_checkpoint(model.model, list(by_id.values()))
        else:
            print("Reusing saved no-tools baseline:", sample_id, flush=True)

        print("Running tool-assisted agent:", sample_id, flush=True)
        try:
            final = agent.run(item["question"]).to_dict()
        except Exception:
            write_checkpoint(model.model, list(by_id.values()))
            print(
                "Comparison interrupted. Saved progress to reports/sample_comparisons.json. "
                "Rerun this script to resume; successful calls will not repeat.",
                flush=True,
            )
            raise
        record.update({
            "agent_answer": final["response"],
            "agent_tool_calls": final["tool_calls"],
            "agent_citations": final["citations"],
        })
        write_checkpoint(model.model, list(by_id.values()))
        print("Completed and saved:", sample_id, flush=True)

    ordered = [by_id[item["id"]] for item in SAMPLES]
    output = write_checkpoint(model.model, ordered)
    update_readme(ordered)
    print(f"Completed {len(ordered)} comparisons. Wrote {output.relative_to(ROOT)} "
          "and updated the comparison table in README.md.", flush=True)


if __name__ == "__main__":
    main()
