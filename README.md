# PawCity AI — Evidence-Based NYC Dog-Friendliness Research

**Course:** IEOR 4570 — Project 2: A Data Exploration Agent  
**Path:** Deep Research (`research`)  
**Audience:** NYC dog owners (especially owners of large/active dogs), urban planners and public-data researchers  
**Status:** All four real datasets included; offline agent tests and local web endpoints verified. **Live LLM calls and Cloud Run deployment still require credentials/configuration.**

## 1. What does it do?

PawCity answers research questions about **documented** dog-run facilities, dog-license periods, 2025 barking-noise service requests and 2025 reported dog bites in NYC ZIP-code areas. It is designed to identify **evidence gaps**, not to give an ungrounded dog-safety rating. Its central research problem is:

> Where does documented access to fenced dog runs appear limited relative to recorded licensed-dog presence and reported dog-related incidents, and what are the limitations of these comparisons?

A user enters a question in the custom homepage or sends JSON to `POST /chat`. The **Lead** chooses three data domains for a parallel first round. Three specialist **Researchers** independently query local source files in fresh model contexts. The Lead evaluates whether another domain would resolve a gap (maximum two research rounds). The **Writer** synthesizes the findings and attaches source tags and clickable source links. User requests that are too ambiguous must be clarified, and the system must state when evidence cannot answer a question.

### Project 1 `/chat` response compatibility

PawCity accepts `POST /chat` requests with `{ "message": "...", "session_id": "optional" }`, matching the Project 1 `ChatRequest` fields. Responses retain the Project 1 required keys `response`, `session_id`, and `tool_calls`. New session IDs are UUID strings; if the client provides a session ID, the service echoes it back. This ID is used for request/response compatibility, **not as a durable session-memory store**.

Each Researcher tool call includes the original `name`, `args`, and `result` fields plus the required `agent` identifier and a research `round`; `arguments` remains available as a compatibility alias for existing frontend code. Extra fields `citations`, `agent_trace`, `answer`, and `clarification_needed` power the PawCity evidence UI. Lead and Writer actions are recorded in `agent_trace` rather than falsely represented as data-tool calls. The live service may respond with a 503 error when its model key or rate limit prevents research.

Example response envelope (illustrative, not a live answer):

```json
{
  "response": "Documented findings [PARKS]",
  "session_id": "cdb0ef67-24f7-469a-8d15-53ec97a813e7",
  "tool_calls": [{
    "agent": "researcher_parks",
    "name": "query_parks",
    "args": {"zip_codes": ["10001", "10002"]},
    "result": {"source_id": "PARKS", "rows": []},
    "round": 1
  }]
}
```

### Agent flow

```text
User question
    ↓
Lead Agent: scope selection, plan, clarify if vague
    ↓
Parallel fresh-context Researchers (three source specialties)
    ↓
Lead Agent: review evidence gaps → optional additional Researcher (turn cap = 2)
    ↓
Writer Agent: cited synthesis + explicit limitations
    ↓
/chat JSON: response, session_id, tool_calls[agent, name, args, result], plus citations and agent_trace
```

Researcher sub-agent tool calls appear in `tool_calls` with their `agent` identifiers and their exact structured evidence. Agent planning and synthesis actions appear in `agent_trace`. Each API model call is independent rather than a shared evolving transcript.

## 2. Actual data, provenance, and loading

The author downloaded the grouped/facility-level extracts from NYC Open Data on **November 10, 2026**. Exact time stamps, official source URLs and the full original API query URLs are stored in `data/metadata/query_log.json`. They are included in this repository so the grader does **not** have to download data again.

| Source | Official dataset | Included file | Grain / coverage |
|---|---|---|---|
| NYC Parks Dog Runs | [hxx3-bwgv](https://data.cityofnewyork.us/d/hxx3-bwgv) | `data/raw/dog_runs.csv` | 95 dog-run facility records; some ZIP values are blank or multi-valued |
| NYC Dog Licensing | [nu7n-tubp](https://data.cityofnewyork.us/d/nu7n-tubp) | `data/raw/dog_licenses.csv` | 19,091 ZIP × breed aggregate rows from the **2026** extract; a license period is **not** a unique dog |
| NYC 311 Service Requests | [erm2-nwe9](https://data.cityofnewyork.us/d/erm2-nwe9) | `data/raw/dog_311.csv` | **8,327** 2025 service requests with descriptor `Noise, Barking Dog (NR5)`, grouped into 180 ZIP strings |
| NYC Reported Dog Bites | [rsgh-akpg](https://data.cityofnewyork.us/d/rsgh-akpg) | `data/raw/dog_bites.csv` | 241 grouped ZIP records for **2025** reported incidents |

**Rebuild:** `uv run python scripts/download_data.py --all` (requires a network connection to NYC Open Data). The 311 query is split into twelve month-scoped requests to avoid the timeout encountered during initial data collection. Rebuild `data/processed/zip_summary.csv` and the quality report with:

```bash
uv run python -c "from pathlib import Path; from pawcity.pipeline import make_summary_report; print(make_summary_report(Path('.')))"
```

Data are stored **locally** as aggregated CSVs. No personal licensee names, addresses or individual dog owner records are included. The data are shipped with the Docker image, so Cloud Run does not need an external data download at startup.

For detailed field descriptions, interpretation limits, and extraction methods, see [`DATA_DICTIONARY.md`](DATA_DICTIONARY.md).

**Why this dataset/problem is distinctive:** This project combines independent NYC parks, licensing and two incident-reporting datasets into a domain-specific dog-owner research workflow. Its question domain is about dog-run coverage gaps and evidence adequacy, not the general NYC 311 search, NYC housing lookup or animal shelter/adoption outcome projects in the class sign-up sheet. Registration should be confirmed against the latest shared sheet.

### Data limitations: essential, not optional

- ZIP-code **strings** are not neighborhood boundaries. The joined file includes non-NYC ZIP strings from dog-owner license records. Citywide suggestions use a conservative NYC ZIP pattern filter, **not** authoritative ZIP polygons or a representative sampling design.
- A facility tagged with two ZIP codes contributes to each ZIP's count. **Do not sum ZIP counts** to count distinct facilities. Some facilities have no usable ZIP tag; 95 is the actual source's distinct facility-record count.
- The 2026 license extract and 2025 incidents have different periods. License periods can include renewals and owner ZIP locations, whereas the incident reports use event ZIPs.
- Barking-service-request volumes can reflect reporting patterns or multiple requests about the same issue; they are *not* all dog-related 311 reports.
- Dog-bite reports can be incomplete. With no matched denominators, per-dog bite risk and causal effects cannot be inferred.
- Off-leash permitted areas beyond fenced runs, distance from a home, park size and the quality of individual parks are not included.
- If a source failed or is missing, the processed file uses a blank (`NA` in analysis), **never a false zero**, and the live agent fails closed.

## 3. Local setup (Jupyter-friendly)

Requirements: **Python 3.11+**, optional `uv`, and an optional OpenAI API key for genuine LLM research. The server and data processing use Python standard library only; no additional pip package is required.

```bash
uv sync
uv run python -m unittest discover -s tests -v
uv run python app.py
```

Or, without `uv`:

```bash
python -m unittest discover -s tests -v
python app.py
```

Visit **http://localhost:8080**. Read-only data exploration works without a key. The **live AI research** endpoint requires `OPENAI_API_KEY` securely configured in the server's environment. Do not put API keys in source files, commit histories, screenshots or notebooks. Model defaults to `gpt-4.1-mini`; change with `PAWCITY_MODEL`. The cost of actual model calls depends on your API account.

Open **`PawCity_Complete.ipynb`** in JupyterLab for a completely English notebook covering source verification, offline tests, evidence queries and an optional live model test. If you run the server from inside Jupyter, use a separate terminal or start it using `subprocess` instead of keeping a cell blocked on `serve_forever()`.

### Sample `/chat` request

```bash
curl -X POST http://localhost:8080/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Compare ZIP 10001 and 10002 using dog runs, 2025 barking reports, licenses and bite reports."}'
```

**Response shape (verified against the actual Project 1 `app(5).py` reference):**

```json
{
  "response": "Source-cited research text ...",
  "session_id": "example-session-id",
  "tool_calls": [{"agent":"researcher_parks","name":"query_parks","args":{"zip_codes":["10001","10002"]},"result":{"source_id":"PARKS","rows":[]},"round":1}],
  "citations": [{"id":"PARKS","title":"NYC Parks Dog Runs","url":"https://data.cityofnewyork.us/d/hxx3-bwgv"}],
  "agent_trace": [{"agent":"lead","action":"plan"}],
  "answer": "Source-cited research text ...",
  "clarification_needed": false
}
```

This JSON is **an illustrative schema**, not a claim about an actual completed research answer. The actual GradPath Project 1 `app(5).py` reference has now been inspected: the required response fields are exactly `response`, `session_id` and `tool_calls`. PawCity preserves those fields while adding `agent` to each Researcher tool call. See [`PROJECT1_COMPATIBILITY.md`](PROJECT1_COMPATIBILITY.md) for differences, including the fact that PawCity does not currently implement GradPath-style cross-turn memory.

## 4. Three grader sample questions: exact data-backed expectations

Expected values below were computed from the included real CSV snapshots. For each question, compare them with the **same model** called directly with **no tools and no system prompt**. The direct model may guess incorrectly; do not confuse these offline facts with a verified live model evaluation.

| Grader prompt | Expected answer from included data | Source |
|---|---|---|
| **1. Which NYC ZIP codes have the most documented dog runs?** | ZIP **10024** has **5** dog-run facilities tagged to it. ZIPs **10040**, **10471**, and **11201** each have **3**. This is tagged facilities by ZIP, not all off-leash access. | `data/raw/dog_runs.csv`; `data/processed/zip_summary.csv` (`dog_runs`) |
| **2. Which NYC ZIP areas have no recorded dog runs despite many license periods?** | Examples: **10025** has **0** recorded runs and **2,175** license periods; **10023** has **0** and **1,957**; **10128** has **0** and **1,597**. A ZIP with no tagged facility could still be close to a facility in an adjoining ZIP. | `data/processed/zip_summary.csv` (`dog_runs`, `license_periods`); `data/raw/dog_licenses.csv` |
| **3. Compare ZIP 10001 and 10002 for dog runs, 2025 barking requests, license periods and bite reports.** | **10001:** 0 runs, 811 license periods (2026 extract), 45 barking requests (2025), 15 reported bites (2025). **10002:** 2 runs, 1,070 license periods, 72 barking requests, 16 reported bites. These are incomparable denominators, not a safety ranking. | `data/processed/zip_summary.csv`; all four raw CSVs and `data/metadata/query_log.json` |

### Side-by-side comparison against the same model with no tools or system prompt

`uv run python scripts/compare_samples.py` calls the same OpenAI model twice for each question: (1) with only the bare question, **without tools or a system prompt**, and (2) through the full multi-agent pipeline. It checkpoints baseline responses immediately and full agent responses after each question in `reports/sample_comparisons.json`, so rerunning after an API rate limit resumes without repeating completed calls. Once all questions finish, it updates the block below. API calls are paced across parallel researchers using `PAWCITY_API_RPM` (default 7 requests/minute; adjust for your account limit). **This command requires a real API key. No model answers have been invented for this README.**

<!-- COMPARISON_RESULTS_START -->
| Question | Same model, no tools or system prompt | Tool-enabled PawCity agent |
|---|---|---|
| Dog runs by ZIP | **NOT RUN:** requires API credentials | **NOT RUN:** requires API credentials |
| ZIPs with many license periods and no tagged dog run | **NOT RUN:** requires API credentials | **NOT RUN:** requires API credentials |
| ZIP 10001 vs 10002 | **NOT RUN:** requires API credentials | **NOT RUN:** requires API credentials |
<!-- COMPARISON_RESULTS_END -->

Do not submit a final README with this comparison block untested if the grader expects actual side-by-side responses. A real API-enabled run must also be manually checked for citation correctness and unsupported claims.

## 5. Path requirements and testing

**Implemented in code** (subject to live LLM verification): three agent shapes; Lead plans parallel fan-out to three independent Researchers via `ThreadPoolExecutor`; dedicated fresh-context calls; gap review with a maximum of two research rounds; clarification of vague inputs; a cited Writer; sub-agent tool calls logged with `agent`; and user-visible source links. `python -m unittest discover -s tests -v` runs unit tests with labeled mock LLM responses, verifies evidence metadata, multi-ZIP handling, missing source behavior and the parallel/gap flow. Mock testing does **not** establish real LLM quality.

The app includes an original custom frontend (research question composer, suggested prompts, live source status, ZIP evidence preview, cited research results and expandable agent/tool traces). It serves `/health`, `/api/summary`, `/api/provenance`, `/api/quality`, and `/chat`.

## 6. Deployment to Google Cloud Run

1. Create a GitHub repository with the **contents of this directory at the repository root**. Keep the included grouped CSV files; all are well below GitHub's 100 MB limit.
2. Test locally with `python app.py`. Docker (optional): `docker build -t pawcity-ai .` then `docker run --rm -p 8080:8080 -e OPENAI_API_KEY="$OPENAI_API_KEY" pawcity-ai`.
3. In Google Cloud Console select **Cloud Run → Create Service → Continuous deployment from repository**; connect the GitHub repo and select the Dockerfile build. Choose the correct Google Cloud project and region. Configure `OPENAI_API_KEY` via **Secret Manager**, not a committed `.env` file. Set the request timeout high enough for the agent (for example, **300 seconds**) and define `PAWCITY_MAX_TURNS=2`.
4. Follow the instructor’s Cloud Run deployment guide: when deploying under the Columbia GCP organization, configure **Require authentication → Identity-Aware Proxy (IAP)** and the specified Columbia access policy, then verify that graders can log in and access `/health` and `/chat`. Do not expose an unrestricted public service contrary to the course guide. Keep the service available until grades are released.
5. Update `submission.json` with the actual URL and **every team member's UNI** (the only UNI known from the conversation is `yw4616`), then run `python validate_submission.py`. One teammate submits the GitHub URL to Courseworks.
6. If using a private repo, grant access to the four GitHub usernames specified in the assignment.

**Cloud Run and GitHub have not been provisioned in this archive.** The blank deployment URL in `submission.json` must be replaced before submission. Secret configuration, API billing, publicly reachable site verification and the final GitHub submission require account access.

## 7. Rubric readiness (25 points)

| Category | Weight | Current status |
|---|---:|---|
| Basics | 1 | README and submission.json present; submission URL and any additional authors **still incomplete** |
| Functionality | 9 | Local site and offline-tested agent integrated; real LLM quality and Cloud Run reachability **unverified** |
| Data | 4 | Four real datasets and provenance included; known limitations handled; distinct research problem selected |
| Deep Research path | 7 | Lead, parallel independent Researchers, gap review, clarifications and Writer implemented; live API evaluation **pending** |
| Creativity | 4 | Custom PawCity website and cross-source dog-owner exploration scenario |

### Final submission checklist

- [ ] Run a **real** API-enabled research session and inspect source citations/tool traces.
- [ ] Run `scripts/compare_samples.py` to populate the exact same-model comparisons above.
- [x] Inspect the actual final GradPath Project 1 `app(5).py` and verify the `/chat` response envelope; sub-agent calls include `agent`.
- [ ] Verify all team members and one or more data sources per member.
- [ ] Deploy GitHub continuous deployment to Cloud Run with the instructor-specified IAP access policy, and test end-to-end.
- [ ] Put the real HTTPS URL and the full team UNI list in `submission.json`.
- [ ] Keep the service up until grading is complete.

## 8. Rate-limit-safe comparison reruns

If the project must run with a model quota of 10 requests per minute, open `PawCity_Resume_Comparisons.ipynb` and run its cells in order. A shared, process-local request pacer defaults to 7 requests per minute; HTTP 429 rate-limit responses are retried with backoff. The comparison script saves each baseline immediately and each full agent report as soon as it completes. Rerunning after an interruption reuses those checkpoints. Responses from runs made with the older, non-checkpointing script cannot be recovered unless previously saved elsewhere. No results in this repository are fabricated.
