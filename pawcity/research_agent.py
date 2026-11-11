"""PawCity Deep Research: Lead -> parallel fresh-context Researchers -> Writer.

Live research uses Google Cloud Vertex AI Gemini through Application Default Credentials.
No simulated research findings are presented as genuine model outputs. Every data researcher
reads locally shipped source snapshots using explicit, logged Python tools.
"""
from __future__ import annotations

import json
import os
import re
import time
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import quote

from pawcity.pipeline import normalize_zip, parse_zip_tags, read_csv

SOURCE = {
    "parks": ("PARKS", "NYC Parks Dog Runs", "https://data.cityofnewyork.us/d/hxx3-bwgv", "dog_runs", "dog_runs"),
    "licenses": ("LICENSES_2026", "NYC Dog Licensing (2026 extract)", "https://data.cityofnewyork.us/d/nu7n-tubp", "dog_licenses", "license_periods"),
    "barking": ("BARKING_2025", "NYC 311 Barking Dog noise requests (2025)", "https://data.cityofnewyork.us/d/erm2-nwe9", "dog_311", "dog_related_311"),
    "bites": ("BITES_2025", "NYC reported dog bites (2025)", "https://data.cityofnewyork.us/d/rsgh-akpg", "dog_bites", "reported_bites"),
}
DOMAINS = tuple(SOURCE)
DATA_LIMITS = (
    "ZIP areas are not neighborhoods or walking-distance measures. Some dog runs are tagged with multiple ZIPs; "
    "summing ZIP counts double-counts such facilities. License periods are not unique dogs and use the 2026 extract; "
    "barking requests and bite incidents are from 2025. Barking data covers ONLY 'Noise, Barking Dog (NR5)' "
    "requests; it is not all dog-related 311 activity. Complaint and bite counts are subject to reporting biases. "
    "License ZIP and incident ZIP fields describe different populations or locations; do not assume equivalent geographic denominators. "
    "These records cannot establish dog safety, causation, per-dog risk, or an overall neighborhood ranking."
)


def known_nyc_zip(code: str) -> bool:
    """Conservative scope guard, not an authoritative NYC ZIP boundary table."""
    return code.startswith(("100", "101", "102", "103", "104", "111", "112", "113", "114", "116")) or code in {"11004", "11005"}


def parse_zips(text: str | None) -> list[str]:
    return parse_zip_tags(text)


def int_or_none(value: str | int | None) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def screen_for_clarification(question: str) -> str | None:
    q = (question or "").strip()
    if len(q) < 12 or q.lower() in {"which is best?", "is nyc good?", "good for dogs?", "best neighborhood?"}:
        return ("Please specify a question and comparison scope. Example: Compare ZIP 10001 and 10002 "
                "using recorded dog runs, license periods, 2025 barking complaints, and bite reports.")
    if not re.search(r"(?<!\d)\d{5}(?!\d)", q) and re.search(
        r"\b(williamsburg|upper west side|chelsea|soho|bushwick|astoria|greenpoint)\b", q, re.I
    ):
        return ("The current snapshot is organized by ZIP code, not named neighborhood. "
                "Please specify two or more five-digit ZIP codes to compare, or ask a citywide question.")
    return None


class DataTools:
    """Deterministic source tools. Only loads the supplied, auditable CSV files."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.log_path = self.root / "data/metadata/query_log.json"
        if not self.log_path.exists():
            raise FileNotFoundError("Missing provenance log: data/metadata/query_log.json")
        self.log = json.loads(self.log_path.read_text(encoding="utf-8"))
        for domain, (_, _, _, data_file, _) in SOURCE.items():
            if self.log.get(data_file, {}).get("status") != "ok":
                raise RuntimeError(f"Data source {data_file} was not verified; missing is not zero.")
            if not (self.root / "data/raw" / f"{data_file}.csv").is_file():
                raise FileNotFoundError(f"Missing snapshot: data/raw/{data_file}.csv")
        if "Barking Dog" not in self.log["dog_311"].get("complaint_scope", ""):
            raise RuntimeError("311 snapshot is not the documented Barking Dog subset")
        if self.log["dog_311"].get("event_year") != 2025 or self.log["dog_bites"].get("event_year") != 2025:
            raise RuntimeError("Expected 2025 incident extracts; check provenance")
        self.rows = read_csv(self.root / "data/processed/zip_summary.csv")
        self.index = {r["zip_code"]: r for r in self.rows if normalize_zip(r.get("zip_code"))}
        self.runs = read_csv(self.root / "data/raw/dog_runs.csv")
        self.nyc_rows = [r for r in self.rows if known_nyc_zip(r["zip_code"])]

    def candidates(self, question: str, limit: int = 8) -> tuple[list[str], str]:
        """A grounded shortlist for citywide questions; NOT a safety ranking."""
        zips = list(dict.fromkeys(re.findall(r"(?<!\d)\d{5}(?!\d)", question)))
        if zips:
            return zips[:12], "ZIP codes explicitly supplied by the user"
        q = question.lower()
        if any(term in q for term in ("no dog run", "without dog run", "few dog run", "zero dog run", "underserved")):
            ranks = sorted((r for r in self.nyc_rows if int_or_none(r.get("dog_runs")) == 0),
                           key=lambda r: int_or_none(r.get("license_periods")) or 0, reverse=True)
            label = "Top ZIPs with zero tagged dog runs sorted by license periods (not dog counts)"
        elif any(term in q for term in ("bark", "complaint", "noise")):
            ranks = sorted(self.nyc_rows,
                           key=lambda r: int_or_none(r.get("dog_related_311")) or 0, reverse=True)
            label = "Highest recorded 2025 barking requests among conservatively scoped NYC ZIPs"
        elif ("dog run" in q and any(term in q for term in ("most", "highest", "largest", "top", "number", "count"))):
            ranks = sorted(self.nyc_rows, key=lambda r: int_or_none(r.get("dog_runs")) or 0, reverse=True)
            label = "Highest tagged dog-run count among conservatively scoped NYC ZIPs"
        elif any(term in q for term in ("bite", "incident")):
            ranks = sorted(self.nyc_rows, key=lambda r: int_or_none(r.get("reported_bites")) or 0, reverse=True)
            label = "Highest 2025 reported bite counts, not risk rates"
        else:
            ranks = sorted(self.nyc_rows, key=lambda r: int_or_none(r.get("license_periods")) or 0, reverse=True)
            label = "Illustrative high-license-period ZIPs, not a representative citywide sample"
        return [r["zip_code"] for r in ranks[:limit]], label

    def query(self, domain: str, zips: list[str], limit: int = 12) -> dict[str, Any]:
        if domain not in SOURCE:
            raise ValueError(f"Unsupported research source: {domain}")
        if not zips or len(zips) > limit or any(normalize_zip(z) != z for z in zips):
            raise ValueError("Provide 1–12 distinct five-digit ZIP codes")
        source_id, title, url, data_file, metric = SOURCE[domain]
        results = []
        for z in list(dict.fromkeys(zips)):
            record = self.index.get(z)
            row = {"zip_code": z, "metric": metric, "value": int_or_none(record.get(metric)) if record else None,
                   "in_conservative_nyc_zip_scope": known_nyc_zip(z)}
            if domain == "parks":
                facilities = [{"name": item.get("name"), "objectid": item.get("objectid"),
                               "multiple_zip_tags": len(parse_zip_tags(item.get("zipcode"))) > 1}
                              for item in self.runs if z in parse_zip_tags(item.get("zipcode"))]
                row["facilities"] = facilities[:30]
                row["facility_match_count"] = len(facilities)
            results.append(row)
        meta = self.log[data_file]
        return {
            "source_id": source_id, "source_title": title, "source_url": url,
            "data_file": f"data/raw/{data_file}.csv", "rows": results,
            "coverage": {key: meta.get(key) for key in ("event_year", "license_extract_year", "complaint_scope", "retrieved_at_utc")
                         if key in meta},
            "limitations": DATA_LIMITS,
        }

    def inventory(self) -> dict[str, Any]:
        return {"sources": {domain: {"source_id": SOURCE[domain][0],
                                      "raw_record_groups": self.log[SOURCE[domain][3]].get("rows"),
                                      "source_url": SOURCE[domain][2]} for domain in DOMAINS},
                "nyc_zip_rows_conservative": len(self.nyc_rows),
                "all_zip_strings_across_sources": len(self.rows),
                "barking_2025_requests": sum(int_or_none(r.get("reports")) or 0 for r in read_csv(self.root / "data/raw/dog_311.csv")),
                "distinct_dog_run_records": len(self.runs),
                "limitations": DATA_LIMITS}


# A single-process request pacer bounds parallel researcher API call starts.
# Multiple Cloud Run instances may require Cloud Run concurrency limits.
_api_pace_lock = threading.Lock()
_api_next_request_at = 0.0


def pace_api_request() -> None:
    """Limit Vertex AI request starts across researcher threads (7 RPM by default)."""
    global _api_next_request_at
    rpm = max(1.0, min(1000.0, float(os.getenv("PAWCITY_API_RPM", "7"))))
    interval = 60.0 / rpm
    with _api_pace_lock:
        now = time.monotonic()
        scheduled = max(now, _api_next_request_at)
        _api_next_request_at = scheduled + interval
    delay = scheduled - now
    if delay > 0:
        time.sleep(delay)


def google_access_token() -> str:
    """Acquire a short-lived OAuth token, never persist credentials in this repo."""
    if os.getenv("K_SERVICE"):
        request = Request(
            "http://metadata.google.internal/computeMetadata/v1/instance/"
            "service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"},
        )
        try:
            with urlopen(request, timeout=5) as result:
                token_data = json.loads(result.read().decode("utf-8"))
            return token_data["access_token"]
        except (URLError, HTTPError, OSError, KeyError, ValueError) as exc:
            raise RuntimeError(
                "Cannot obtain Cloud Run service account token from metadata server."
            ) from exc
    try:
        output = subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            capture_output=True, text=True, timeout=20, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            "Local Google Cloud credentials unavailable. Install the Google Cloud CLI "
            "and run: gcloud auth application-default login"
        ) from exc
    token = output.stdout.strip()
    if not token:
        raise RuntimeError("gcloud returned an empty Google Cloud access token")
    return token


class GeminiModel:
    """Stateless Vertex AI Gemini via REST and Google Cloud OAuth credentials.

    The local developer authenticates with gcloud Application Default
    Credentials. Cloud Run uses the attached runtime service identity.
    No Google API key, JSON key file, or external pip dependency is needed.
    """

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("PAWCITY_MODEL", "gemini-3.5-flash-lite")
        self.project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        if not self.project:
            raise RuntimeError("Set GOOGLE_CLOUD_PROJECT to your school GCP project ID.")
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", self.project):
            raise ValueError("GOOGLE_CLOUD_PROJECT does not look like a project ID")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", self.location):
            raise ValueError("Invalid GOOGLE_CLOUD_LOCATION")

    def _generate_once(self, content: str, instructions: str | None) -> str:
        project = quote(self.project, safe="")
        model = quote(self.model, safe="")
        location = quote(self.location, safe="")
        host = "aiplatform.googleapis.com" if self.location == "global" else f"{self.location}-aiplatform.googleapis.com"
        url = (f"https://{host}/v1/projects/{project}/locations/{location}/"
               f"publishers/google/models/{model}:generateContent")
        payload = {
            "contents": [{"role": "user", "parts": [{"text": content}]}],
            "generationConfig": {"temperature": 0.1},
        }
        # IMPORTANT: omit systemInstruction completely for the README baseline.
        if instructions is not None:
            payload["systemInstruction"] = {"parts": [{"text": instructions}]}
        raw = json.dumps(payload).encode("utf-8")
        req = Request(url, data=raw, headers={
            "Authorization": "Bearer " + google_access_token(),
            "Content-Type": "application/json",
            "X-Goog-User-Project": self.project,
        }, method="POST")
        with urlopen(req, timeout=70) as response:
            result = json.loads(response.read().decode("utf-8"))
        answers = [part["text"] for candidate in result.get("candidates", [])
                   for part in candidate.get("content", {}).get("parts", [])
                   if isinstance(part, dict) and isinstance(part.get("text"), str)
                   and not part.get("thought")]
        if not answers:
            raise RuntimeError("Vertex AI Gemini returned no text (check model permissions or safety filters)")
        return "\n".join(answers).strip()

    def request(self, content: str, instructions: str | None = None) -> str:
        for attempt in range(4):
            pace_api_request()
            try:
                return self._generate_once(content, instructions)
            except HTTPError as exc:
                code = exc.code
                if code not in {429, 500, 502, 503, 504} or attempt == 3:
                    raise RuntimeError(
                        f"Vertex AI Gemini HTTP {code}. Check GCP project, model availability, "
                        "billing, Vertex AI API, and IAM (roles/aiplatform.user)."
                    ) from exc
                delay = min(20.0, 3.0 * (2 ** attempt))
                print(f"Vertex AI HTTP {code}; retry {attempt+1}/3 after {delay:g}s.", flush=True)
                time.sleep(delay)
            except (URLError, TimeoutError) as exc:
                if attempt == 3:
                    raise RuntimeError("Could not reach the Vertex AI Gemini endpoint") from exc
                time.sleep(min(20.0, 3.0 * (2 ** attempt)))
        raise RuntimeError("Vertex AI Gemini request could not be completed")

    def __call__(self, role: str, instructions: str, content: str) -> str:
        return self.request(content, instructions)


# Preserve the old Python import name for existing notebooks.
APIModel = GeminiModel


def json_from_model(text: str) -> dict[str, Any]:
    stripped = re.sub(r"^```(?:json)?\s*", "", text.strip())
    stripped = re.sub(r"\s*```$", "", stripped)
    result = json.loads(stripped)
    if not isinstance(result, dict):
        raise ValueError("A model JSON object was expected")
    return result


@dataclass
class ResearchResult:
    answer: str
    citations: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    agent_trace: list[dict[str, Any]]
    clarification_needed: bool = False

    def to_dict(self) -> dict:
        return {"response": self.answer, "answer": self.answer, "citations": self.citations,
                "tool_calls": self.tool_calls, "agent_trace": self.agent_trace,
                "clarification_needed": self.clarification_needed}


class PawCityResearch:
    """Bounded Lead fan-out and gap review, researchers in parallel fresh contexts."""
    def __init__(self, root: str | Path, llm: Callable | None = None, max_turns: int = 2):
        self.tools = DataTools(root)
        self.llm = llm if llm is not None else APIModel()
        if not 1 <= max_turns <= 3:
            raise ValueError("max_turns must be between 1 and 3")
        self.max_turns = max_turns

    def _call(self, role: str, instructions: str, payload: dict | str) -> str:
        return self.llm(role, instructions, json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else payload)

    def run(self, question: str) -> ResearchResult:
        question = str(question or "").strip()
        clarification = screen_for_clarification(question)
        if clarification:
            return ResearchResult(clarification, [], [], [{"agent": "lead", "action": "clarification"}], True)
        selected_zips, selection_basis = self.tools.candidates(question)
        instruction = (
            "You are the PawCity Lead, planning NYC dog data research. Return ONLY JSON with keys "
            "clarification (null or string), domains (array of EXACTLY three distinct entries among "
            "parks,licenses,barking,bites), focus (short string). Select three relevant sources to research "
            "in parallel; leave a fourth for potential follow-up. No inferred neighborhood ZIP mapping. "
            "If the question is ambiguous or unsupported, request clarification. "
            "Do not give an answer in this planning step."
        )
        plan = json_from_model(self._call("lead", instruction,
                                         {"question": question, "selected_zip_codes": selected_zips,
                                          "selection_basis": selection_basis, "sources": list(DOMAINS)}))
        if plan.get("clarification"):
            return ResearchResult(str(plan["clarification"]), [], [], [{"agent": "lead", "action": "clarification"}], True)
        domains = [d for d in plan.get("domains", []) if d in SOURCE]
        domains = list(dict.fromkeys(domains))
        for d in DOMAINS:
            if len(domains) >= 3:
                break
            if d not in domains:
                domains.append(d)
        domains = domains[:3]
        focus = str(plan.get("focus", "Compare reported records; do not infer dog safety"))
        traces = [{"agent": "lead", "action": "plan", "domains": domains,
                   "zip_codes": selected_zips, "selection_basis": selection_basis, "focus": focus}]
        tool_calls = []
        findings = []
        used_domains = set()
        for research_round in range(1, self.max_turns + 1):
            def researcher(domain: str) -> tuple[dict, dict]:
                evidence = self.tools.query(domain, selected_zips)
                summary = self._call(f"researcher_{domain}",
                                     "You are an independent specialist RESEARCHER. This is a FRESH context: "
                                     "you have only your assigned source evidence, not other researchers' output. "
                                     "Use only the structured tool data. Give a concise factual English summary "
                                     "and cite its source_id as a bracketed marker. Treat missing as unknown. "
                                     "Do not infer dog safety or causal effects or unique dogs.",
                                     {"question": question, "focus": focus, "tool_result": evidence})
                return ({"agent": f"researcher_{domain}", "source_id": evidence["source_id"],
                         "summary": summary, "evidence": evidence},
                        {"agent": f"researcher_{domain}", "name": f"query_{domain}",
                         "args": {"zip_codes": selected_zips},
                         "arguments": {"zip_codes": selected_zips}, "result": evidence,
                         "round": research_round})

            with ThreadPoolExecutor(max_workers=len(domains)) as executor:
                futures = [executor.submit(researcher, domain) for domain in domains]
                for future in as_completed(futures):
                    finding, call = future.result()
                    findings.append(finding)
                    tool_calls.append(call)
                    traces.append({"agent": finding["agent"], "action": "research", "round": research_round})
            used_domains.update(domains)
            if research_round >= self.max_turns:
                break
            review = json_from_model(self._call("lead", (
                "You are the PawCity Lead checking research coverage. JSON ONLY with keys "
                "needs_followup (boolean), follow_up_domains (array of source domain strings), "
                "reason (short string). Explore an unqueried domain ONLY if it could fill a genuine "
                "evidence gap. Never repeat a source or assume additional data exist."),
                {"question": question, "reviewed_domains": sorted(used_domains),
                 "summaries": [{"source_id": x["source_id"], "summary": x["summary"]} for x in findings],
                 "possible_new_domains": [d for d in DOMAINS if d not in used_domains]}))
            traces.append({"agent": "lead", "action": "gap_review", "review": review})
            if not review.get("needs_followup"):
                break
            domains = [d for d in review.get("follow_up_domains", []) if d in SOURCE and d not in used_domains]
            domains = list(dict.fromkeys(domains))
            if not domains:
                break
        seen_tags = {finding["source_id"] for finding in findings}
        citations = [{"id": tag, "title": title, "url": url}
                     for tag, title, url, _, _ in SOURCE.values() if tag in seen_tags]
        citations.extend([
            {"id": "QUALITY", "title": "Dataset limitations", "url": "/api/quality"},
            {"id": "PROVENANCE", "title": "Exact source queries and retrieval times", "url": "/api/provenance"}])
        answer = self._call("writer", (
            "You are the final PawCity Writer. Create a short, evidence-grounded research report in English. "
            "Include: Findings, Evidence, Uncertainties and missing data, and a one-sentence conclusion. "
            "Every claim with a number MUST include a bracketed source tag from the given citations "
            "such as [PARKS] or [BARKING_2025]. Never invent values, missing sources, neighborhood "
            "boundaries, walking distances, rates or causal claims. Explicitly state if the data cannot "
            "answer the question. The 2025 barking subset is not all 311 dog complaints."),
            {"question": question, "researcher_findings": findings,
             "selection_basis": selection_basis, "limitations": DATA_LIMITS, "allowed_citations": citations})
        traces.append({"agent": "writer", "action": "synthesis"})
        if not any(f"[{s}]" in answer for s in seen_tags):
            raise ValueError("Writer report has no dataset citation; refusing uncited result")
        return ResearchResult(answer, citations, tool_calls, traces)
