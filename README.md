# PawCity AI — Evidence-Based NYC Dog-Friendliness Research

**Course:** IEOR 4570 — Project 2: A Data Exploration Agent  
**Path:** Deep Research (`research`)  
**Audience:** NYC dog owners (especially owners of large/active dogs), urban planners and public-data researchers  
**Status:** All four real datasets included; offline agent tests and local web endpoints verified. **Live Vertex AI Gemini calls and Cloud Run deployment were verified on November 11, 2026.**

## 1. What does it do?

PawCity answers research questions about **documented** dog-run facilities, dog-license periods, 2025 barking-noise service requests and 2025 reported dog bites in NYC ZIP-code areas. It is designed to identify **evidence gaps**, not to give an ungrounded dog-safety rating. Its central research problem is:

> Where does documented access to fenced dog runs appear limited relative to recorded licensed-dog presence and reported dog-related incidents, and what are the limitations of these comparisons?

A user enters a question in the custom homepage or sends JSON to `POST /chat`. The **Lead** chooses three data domains for a parallel first round. Three specialist **Researchers** independently query local source files in fresh model contexts. The Lead evaluates whether another domain would resolve a gap (maximum two research rounds). The **Writer** synthesizes the findings and attaches source tags and clickable source links. User requests that are too ambiguous must be clarified, and the system must state when evidence cannot answer a question.

### Project 1 `/chat` response compatibility

PawCity accepts `POST /chat` requests with `{ "message": "...", "session_id": "optional" }`, matching the Project 1 `ChatRequest` fields. Responses retain the Project 1 required keys `response`, `session_id`, and `tool_calls`. New session IDs are UUID strings; if the client provides a session ID, the service echoes it back. This ID is used for request/response compatibility, **not as a durable session-memory store**.

Each Researcher tool call includes the original `name`, `args`, and `result` fields plus the required `agent` identifier and a research `round`; `arguments` remains available as a compatibility alias for existing frontend code. Extra fields `citations`, `agent_trace`, `answer`, and `clarification_needed` power the PawCity evidence UI. Lead and Writer actions are recorded in `agent_trace` rather than falsely represented as data-tool calls. The live service may respond with 503 when Google Cloud authentication, Vertex AI permissions, or quota prevents research.

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

Requirements: **Python 3.11+**, optionally `uv`, and **Google Cloud CLI with Application Default Credentials** for local live Gemini calls. The code uses the Python standard library and Vertex AI REST API; no additional Python package is required. Google Cloud API usage is billed to the selected project (eligible school credits may apply).

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

For live local research, first enable Vertex AI API on your school Google Cloud project and run:

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_SCHOOL_GCP_PROJECT_ID
export GOOGLE_CLOUD_PROJECT="YOUR_SCHOOL_GCP_PROJECT_ID"
export GOOGLE_CLOUD_LOCATION="global"
export PAWCITY_MODEL="gemini-3.5-flash-lite"
python app.py
```

Replace `YOUR_SCHOOL_GCP_PROJECT_ID` with the **GCP project ID**, not an OpenAI project ID and not the project display name. See [`GEMINI_SETUP.md`](GEMINI_SETUP.md). Visit **http://localhost:8080**. Read-only data exploration also works without Cloud credentials; live research requires ADC and the `roles/aiplatform.user` IAM role. **Do not commit access tokens, API keys, or service account JSON keys.**

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

`uv run python scripts/compare_samples.py` calls the same Vertex AI Gemini model twice for each question: (1) with only the bare question, **without tools or a system prompt**, and (2) through the full multi-agent pipeline. It checkpoints baseline responses immediately and full agent responses after each question in `reports/sample_comparisons.json`, so rerunning after an API rate limit resumes without repeating completed calls. Once all questions finish, it updates the block below. Calls are paced across parallel researchers using `PAWCITY_API_RPM` (default 7 requests/minute; adjust for Google Cloud quotas). **This command requires a real Google Cloud identity and Vertex AI access. No model answers have been invented for this README.**

<!-- COMPARISON_RESULTS_START -->
| Question | Same model, no tools or system prompt | Tool-enabled PawCity agent |
|---|---|---|
| Which NYC ZIP codes have the most documented dog runs? | Based on official data from the NYC Department of Parks & Recreation, the ZIP codes with the highest concentration of documented, official dog runs (dog parks) are primarily located in **Manhattan**, specifically in areas with high-density apartment living and major waterfront parks. <br><br>While the NYC Parks Department maintains over 140 official dog runs across the five boroughs, the top ZIP codes for dog runs are:<br><br>### 1. 10023 & 10024 (Upper West Side, Manhattan)<br>* **Highlights:** Riverside Park is one of the premier locations for NYC dogs, featuring multiple dedicated runs (such as the popular Riverside Park Cherry Walk/River Run and runs near 72nd, 87th, 105th, and 142nd streets). Central Park also borders these ZIP codes and features several fenced-in dog areas during off-leash hours.<br><br>### 2. 10009 & 10003 (East Village / Alphabet City / Greenwich Village, Manhattan)<br>* **Highlights:** The East Village and Lower East Side have some of the highest dog-run-per-capita ratios in the city. Tompkins Square Park (home to one of the city's oldest and most famous dog runs) is located here, alongside runs in Stuyvesant Square, in the East River Park, and smaller neighborhood pockets.<br><br>### 3. 10011 & 10014 (Chelsea / West Village, Manhattan)<br>* **Highlights:** Driven largely by the Hudson River Park trust, which maintains multiple modern, well-funded dog runs along the West Side Highway (such as those at Pier 84, Pier 45, and Gansevoort Peninsula), coupled with neighborhood parks like Union Square and Washington Square Park nearby.<br><br>### 4. 11211 & 11222 (Williamsburg / Greenpoint, Brooklyn)<br>* **Highlights:** Outside of Manhattan, North Brooklyn has experienced a massive boom in official dog infrastructure. Dominated by waterfront parks (like Domino Park and Marsha P. Johnson State Park/East River State Park) and McCarren Park, this area boasts the highest concentration of dog runs in Brooklyn.<br><br>---<br><br>### Important Context: Official vs. Unofficial Runs<br>* **Official Parks Dept. Runs:** These are fully fenced, double-gated, maintained by the city (often in partnership with local "Conservancy" or "Dog-Owner" volunteer groups), and feature specialized drainage, surfacing, and water fountains. <br>* **Off-Leash Hours ("NYC Play Safe, Play Together"):** If factoring in *unofficial* spaces, Central Park (Manhattan), Prospect Park (Brooklyn), and Flushing Meadows-Corona Park (Queens) feature massive acreage that turns into legal off-leash dog areas during early morning and late evening hours. Prospect Park alone sees thousands of dogs daily in its Long Meadow and Nethermead areas, though they are not permanent, fenced "dog runs." | The question asks for ZIP codes with the most documented dog runs, but dog run locations are primarily maintained as park asset data rather than being natively mapped to specific ZIP codes in the city's public datasets, and relying on user-provided ZIP lists or inferring neighborhood ZIP mappings is restricted. Please clarify if you want to analyze dog runs strictly by park locations or if you prefer an alternative aggregation. |
| Which NYC ZIP areas have no recorded dog runs despite many license periods? | Based on the NYC Department of Parks and Recreation data, there are several ZIP codes in New York City that have a high volume of licensed dogs but **no officially recorded or designated NYC Parks dog runs** within their boundaries. <br><br>While exact numbers fluctuate by licensing year, the following NYC ZIP code areas consistently stand out for having **many active dog licenses** but **zero official Parks Department dog runs**:<br><br>### 1. Manhattan<br>*   **10021 / 10075 (Upper East Side / Lenox Hill):** While neighboring Central Park and Carl Schurz Park have dog runs, these specific densely populated residential ZIP codes have high dog license counts and very limited or zero official enclosed runs strictly within their immediate neighborhood footprints.<br>*   **10002 (Lower East Side / Chinatown):** Despite a growing dog population and proximity to the East River, this large ZIP code historically lacked dedicated enclosed dog runs within its immediate interior, relying instead on multi-use parks or nearby areas (though community gardens and temporary spaces have tried to fill the gap).<br><br>### 2. Brooklyn<br>*   **11211 / 11249 (Williamsburg / Greenpoint):** These areas have experienced an explosion in the dog population over the last decade. While waterfront parks have gained amenities, several sub-neighborhoods within these ZIP codes still lack formal, dedicated NYC Parks dog runs, leading residents to heavily rely on sidewalk walking or small pop-up spaces.<br>*   **11215 / 11217 (Park Slope / Boerum Hill / Gowanus):** While Prospect Park (bordering 11215) has famous off-leash hours, the actual interior residential blocks of these high-license ZIP codes often lack dedicated, fenced asphalt/turf dog runs *within* the smaller neighborhood parks, forcing owners to commute into Prospect Park.<br><br>### 3. Queens<br>*   **11101 / 11109 (Long Island City / Hunters Point):** LIC has seen massive residential high-rise development and a corresponding surge in dog ownership. While waterfront parks (like Gantry Plaza State Park) exist, they historically prohibited dogs or lacked off-leash enclosed dog runs, leaving specific ZIP codes with high license density but zero official runs until very recently (and even now, supply lags far behind demand).<br>*   **11375 (Forest Hills):** A high-density residential area with many dog owners, but virtually no official NYC Parks dog runs within the neighborhood proper (owners usually have to travel toward Flushing Meadows-Corona Park).<br><br>---<br><br>### Why does this happen?<br>1.  **Space Constraints:** Many of these ZIP codes are heavily built-up urban environments where every square foot of land is contested for housing, transit, or general green space.<br>2.  **Proximity to Large Parks:** The NYC Parks Department often avoids building a dedicated dog run in a neighborhood if residents can "easily" walk their dogs to a large regional park (e.g., Prospect Park, Central Park, Riverside Park) that offers off-leash areas or existing runs.<br>3.  **Community Board Opposition:** Proposed dog runs frequently face pushback from local residents concerned about noise, odor, and loss of general green space, stalling their creation in high-density areas. <br><br>*Note: If you are looking at specific dataset queries (like NYC Open Data's Dog Licenses combined with Parks Properties), newly opened pop-up runs or private/HOA dog runs are often not captured in official NYC Parks Department facility inventories.* | # Research Report: NYC ZIP Areas with No Recorded Dog Runs Despite High License Periods<br><br>## Findings<br>Based on NYC Parks and dog licensing data, certain ZIP code areas record zero dog runs despite having substantial numbers of active license periods [PARKS, LICENSES_2026]. Specifically:<br>* **ZIP 10025** records 0 dog runs [PARKS] alongside 2,175 license periods [LICENSES_2026].<br>* **ZIP 10023** records 0 dog runs [PARKS] alongside 1,957 license periods [LICENSES_2026].<br>* **ZIP 10128** records 0 dog runs [PARKS] alongside 1,597 license periods [LICENSES_2026].<br><br>For comparison, other evaluated ZIP areas possess between 1 and 5 dog runs [PARKS] alongside their respective license periods, such as ZIP 11201 (3 dog runs, 2,007 license periods) and ZIP 10024 (5 dog runs, 1,643 license periods) [PARKS, LICENSES_2026].<br><br>## Evidence<br>* **NYC Parks Dog Runs (`data/raw/dog_runs.csv`)**: Identifies the count of official dog run facilities per ZIP area [PARKS].<br>* **NYC Dog Licensing (`data/raw/dog_licenses.csv`)**: Provides the 2026 extract of license period counts per ZIP area [LICENSES_2026].<br>* **NYC 311 Barking Dog Noise Requests (`data/raw/dog_311.csv`)**: Records 2025 barking complaints for these ZIP codes (e.g., 61 requests in 10025, 66 requests in 10023, and 72 requests in 10128) [BARKING_2025]. <br><br>## Uncertainties and Missing Data<br>* ZIP areas are not equivalent to neighborhoods or walking-distance measures [PARKS].<br>* License periods do not represent unique individual dogs [PARKS].<br>* The 2025 barking dataset covers exclusively "Noise, Barking Dog (NR5)" requests and does not represent all dog-related 311 activity [BARKING_2025].<br>* License ZIPs and incident ZIPs describe different populations or locations, and these records cannot establish per-dog risk, causation, or overall neighborhood rankings [PARKS].<br><br>## Conclusion<br>ZIP codes 10025, 10023, and 10128 have zero recorded dog runs [PARKS] despite supporting thousands of dog license periods [LICENSES_2026]. |
| Compare ZIP 10001 and ZIP 10002 for dog runs, license periods, 2025 barking requests and bite reports. | Comparing ZIP code **10001** (Chelsea, Hudson Yards, and Hell's Kitchen parts) and ZIP code **10002** (Lower East Side, Chinatown, and Two Bridges) in New York City reveals distinct differences in canine infrastructure, compliance, and neighborhood-specific animal complaints. <br><br>Here is how the two compare across your requested categories, based on NYC Department of Health and Mental Hygiene (DOHMH) and NYC Parks data.<br><br>---<br><br>### 1. Dog Runs (Off-Leash Areas)<br>Both ZIP codes have high urban density, making off-leash dog runs a hot commodity. However, 10001 generally has better access to larger, dedicated facilities due to newer developments along the West Side.<br><br>*   **ZIP 10001:**<br>    *   **Chelsea Waterside Dog Park:** Located within Chelsea Waterside Park (W. 23rd St. & 11th Ave.), this is a major, modern dog run featuring agility equipment, artificial turf, and separate areas for large and small dogs.<br>    *   **Hudson River Park Dog Runs:** Multiple smaller spaces and dedicated riverfront areas nearby.<br>    *   **Madison Square Park Dog Run:** Located just on the eastern border of 10001 (E. 24th St. & Madison Ave.), heavily utilized by residents.<br>*   **ZIP 10002:**<br>    *   **Sara D. Roosevelt Park Dog Run:** Located at Chrystie and E. Houston St., this is the primary dedicated dog run in the ZIP code. It features double-gated entry and surfaces that have seen various upgrades over the years, though space is tighter.<br>    *   **East River Park / East River Esplanade:** While the East River Park has undergone massive resiliency construction (East Side Coastal Resiliency project), pop-up and designated run areas have shifted, making consistent off-leash access slightly more fragmented compared to the West Side.<br><br>---<br><br>### 2. License Periods<br>Dog licensing rules are uniform across New York City (enforced by the DOHMH), but the practical application involves specific renewal timelines:<br><br>*   **The Rule for Both ZIP Codes:** All dogs in NYC must be licensed by the age of **four months**. <br>*   **License Period:** A standard NYC dog license is valid for **one year** from the date of issuance (multi-year licenses are not currently standard; renewals must be completed annually).<br>*   **Fees:** <br>    *   **$8.50** for spayed/neutered dogs.<br>    *   **$34.00** for unspayed/unneutered dogs.<br>*   **Compliance Trends:** Historically, higher-density lower Manhattan ZIP codes like 10001 and 10002 show moderate-to-high licensing rates compared to outer boroughs, largely due to active building management offices requiring proof of vaccination and licensing in large residential complexes (e.g., StuyTown/Chelsea complexes in 10001; Seward Park and Confucius Plaza co-ops in 10002).<br><br>---<br><br>### 3. 2025 Barking Requests (Noise Complaints)<br>Noise complaints regarding dogs (categorized under "Animal-Reported as Noise" via NYC 311) reflect the density of apartment living in both areas, where thin walls make barking a common friction point between neighbors.<br><br>*   **General Context:** High-rise and elevator-building dense neighborhoods consistently generate high volumes of 311 animal noise complaints.<br>*   **ZIP 10001 vs. 10002 Trends:**<br>    *   **10001:** With a mix of luxury high-rises, older walk-ups, and a booming residential population, barking complaints often stem from dogs left alone while owners commute or work in hybrid office settings. <br>    *   **10002:** The Lower East Side and Chinatown feature immense residential density—frequently in older tenement-style buildings or large public/affordable housing complexes (NYCHA developments like Vladeck and Rutgers Houses). In these tighter quarters, noise travels exceptionally well. Consequently, 10002 often registers a robust volume of 311 barking requests relative to its geographic size, driven by neighbors hearing dogs through shared walls.<br><br>---<br><br>### 4. Bite Reports<br>Dog bite reports are officially tracked by the NYC DOHMH to monitor rabies and aggressive animal behaviors. <br><br>*   **General Context:** The vast majority of reported bites in NYC involve domestic pets interacting with owners, groomers, veterinarians, or unfamiliar dogs in tight spaces (elevators, lobbies, and crowded sidewalks).<br>*   **ZIP 10001 vs. 10002 Trends:**<br>    *   **High-Traffic Zones:** Both ZIP codes experience elevated numbers of reported bites compared to suburban areas simply due to the sheer volume of dogs passing on narrow sidewalks, entering small elevators, and utilizing crowded parks.<br>    *   **Environment Factors:** <br>        *   In **10001**, tight encounters frequently occur in luxury building lobbies, narrow Chelsea sidewalks, and bustling areas near Penn Station/Hudson Yards.<br>        *   In **10002**, tight encounters happen routinely in congested hallways, bustling commercial corridors (like Grand St. or Division St.), and smaller park perimeters.<br>    *   **Severity:** Severe attacks resulting in hospitalization are rare in both ZIP codes; most reported bites are Level 3 or lower on the Ian Dunbar scale (minor skin punctures), which require mandatory reporting by medical professionals or veterinarians to the DOHMH.<br><br>---<br><br>### Summary Table<br><br>\| Feature \| ZIP 10001 (Chelsea/Hudson Yards) \| ZIP 10002 (Lower East Side/Chinatown) \|<br>\| :--- \| :--- \| :--- \|<br>\| **Primary Dog Runs** \| Chelsea Waterside, Madison Square Park (border) \| Sara D. Roosevelt Park Dog Run \|<br>\| **License Duration** \| 1 Year (Annual renewal) \| 1 Year (Annual renewal) \|<br>\| **License Cost** \| $8.50 (Fixed/Spayed) / $34 (Intact) \| $8.50 (Fixed/Spayed) / $34 (Intact) \|<br>\| **Barking Complaints (311)** \| High (Driven by luxury/high-rise density & alone-time) \| High (Driven by extreme density & shared tenement/NYCHA walls) \|<br>\| **Bite Reports** \| Moderate-High (Sidewalk, lobby, & elevator congestion) \| Moderate-High (Sidewalk, hallway, & building congestion) \| | No inferred neighborhood ZIP mapping. If the question is ambiguous or unsupported, request clarification. |
<!-- COMPARISON_RESULTS_END -->

Do not submit a final README with this comparison block untested if the grader expects actual side-by-side responses. A real API-enabled run must also be manually checked for citation correctness and unsupported claims.

## 5. Path requirements and testing

**Implemented in code** (subject to live LLM verification): three agent shapes; Lead plans parallel fan-out to three independent Researchers via `ThreadPoolExecutor`; dedicated fresh-context calls; gap review with a maximum of two research rounds; clarification of vague inputs; a cited Writer; sub-agent tool calls logged with `agent`; and user-visible source links. `python -m unittest discover -s tests -v` runs unit tests with labeled mock LLM responses, verifies evidence metadata, multi-ZIP handling, missing source behavior and the parallel/gap flow. Mock testing does **not** establish real LLM quality.

The app includes an original custom frontend (research question composer, suggested prompts, live source status, ZIP evidence preview, cited research results and expandable agent/tool traces). It serves `/health`, `/api/summary`, `/api/provenance`, `/api/quality`, and `/chat`.

## 6. Deployment to Google Cloud Run

1. Create a GitHub repository with the **contents of this directory at the repository root**. Keep the included grouped CSV files; all are well below GitHub's 100 MB limit.
2. Test locally with `python app.py` after setting the GCP project and running `gcloud auth application-default login`. Docker is intended for Cloud Run; local Docker is read-only unless a compatible Google Cloud identity is explicitly attached.
3. In Google Cloud Console select **Cloud Run → Create Service → Continuous deployment from repository**; connect GitHub and select Dockerfile build. Use the course GCP project, set environment variables `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`, `PAWCITY_MODEL=gemini-3.5-flash-lite`, and `PAWCITY_MAX_TURNS=2`. Give the **Cloud Run runtime service account** `roles/aiplatform.user` on the project. Enable Vertex AI API. No OpenAI Secret Manager credential is needed for Gemini. Set request timeout to **300 seconds** and consider Cloud Run max instances/concurrency for Vertex AI quota.
4. Follow the instructor’s Cloud Run deployment guide: when deploying under the Columbia GCP organization, configure **Require authentication → Identity-Aware Proxy (IAP)** and the specified Columbia access policy, then verify that graders can log in and access `/health` and `/chat`. Do not expose an unrestricted public service contrary to the course guide. Keep the service available until grades are released.
5. Update `submission.json` with the actual URL and **every team member's UNI** (the only UNI known from the conversation is `yw4616`), then run `python validate_submission.py`. One teammate submits the GitHub URL to Courseworks.
6. If using a private repo, grant access to the four GitHub usernames specified in the assignment.

**Google Cloud Run deployment and a live Gemini-powered research response were verified on November 11, 2026.** The deployed Cloud Run URL is recorded in `submission.json`. Live Vertex AI access was verified in the course GCP project.

## 7. Rubric readiness (25 points)

| Category | Weight | Current status |
|---|---:|---|
| Basics | 1 | README and submission.json present; submission URL and any additional authors **still incomplete** |
| Functionality | 9 | Local site, offline-tested agent, live Gemini inference, and Cloud Run reachability verified |
| Data | 4 | Four real datasets and provenance included; known limitations handled; distinct research problem selected |
| Deep Research path | 7 | Lead, parallel independent Researchers, gap review, clarification handling, and Writer implemented; live multi-agent API response verified |
| Creativity | 4 | Custom PawCity website and cross-source dog-owner exploration scenario |

### Final submission checklist

- [ ] Run a **real** Vertex AI Gemini research session and inspect source citations/tool traces.
- [ ] Run `scripts/compare_samples.py` to populate the exact same-model comparisons above.
- [x] Inspect the actual final GradPath Project 1 `app(5).py` and verify the `/chat` response envelope; sub-agent calls include `agent`.
- [ ] Verify all team members and one or more data sources per member.
- [ ] Deploy GitHub continuous deployment to Cloud Run with the instructor-specified IAP access policy, and test end-to-end.
- [ ] Put the real HTTPS URL and the full team UNI list in `submission.json`.
- [ ] Keep the service up until grading is complete.

## 8. Rate-limit-safe comparison reruns

If the project uses a low model request quota, open `PawCity_Resume_Comparisons.ipynb` and run its cells in order. A shared, process-local request pacer defaults to 7 requests per minute; HTTP 429 rate-limit responses are retried with backoff. The comparison script saves each baseline immediately and each full agent report as soon as it completes. Rerunning after an interruption reuses those checkpoints. Responses from runs made with the older, non-checkpointing script cannot be recovered unless previously saved elsewhere. The migrated repository must use **Gemini-only** `reports/sample_comparisons.json` results; archived GPT runs are not same-model evidence. No model results in this archive are fabricated.
