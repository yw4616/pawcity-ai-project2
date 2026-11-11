# PawCity AI — Alignment with the Actual GradPath Project 1 Reference

## Verified source

The comparison reference is the author's supplied final Project 1 `app(5).py` for **GradPath**, a Columbia academic-planning agent. It uses FastAPI, LiteLLM / Vertex AI Gemini, function tools, and per-session in-memory conversation histories. The GradPath file is a reference for compatibility; it is **not** copied into this Project 2 repository.

## Exact `/chat` request and response contract

The actual Project 1 application defines:

```python
class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    tool_calls: list[dict]
```

PawCity accepts `message` and an optional `session_id`, and returns the same three required response properties. Project 2 adds an `agent` field to every **Researcher tool call**. PawCity keeps the Project 1 `name`, `args`, and `result` fields; it additionally provides evidence metadata (`round`, `citations`, `agent_trace`, `clarification_needed`, and `answer`) for the custom UI.

Example response (illustrative structure, **not** a generated research result):

```json
{
  "response": "Evidence-based answer [PARKS]",
  "session_id": "example-session-id",
  "tool_calls": [
    {
      "name": "query_parks",
      "args": {"zip_codes": ["10001", "10002"]},
      "result": {"source_id": "PARKS", "rows": []},
      "agent": "researcher_parks",
      "round": 1
    }
  ],
  "citations": [{"id": "PARKS", "title": "NYC Parks Dog Runs", "url": "https://data.cityofnewyork.us/d/hxx3-bwgv"}],
  "agent_trace": [{"agent": "lead", "action": "plan"}]
}
```

## Behavioral differences from Project 1

- **GradPath** persists message history and explicitly stated programs in in-memory dictionaries and exposes `POST /clear`. **PawCity** currently echoes or generates session IDs, but its research queries are stateless; it does **not** implement cross-turn conversational memory or GradPath's `/clear` endpoint. These behaviors are not part of the stated Project 2 `/chat` *response-shape* requirement, and should not be presented as implemented.
- **GradPath** calls Vertex AI Gemini via LiteLLM. **PawCity** now calls Vertex AI Gemini via Google Cloud-authenticated REST requests, while preserving its Lead, independent parallel Researchers, gap review, and Writer. Both use Google Cloud; the internal orchestration still differs.
- Source citation links and sub-agent tool traces appear in separate additional fields as well as the natural-language `response`.

## Testing

Run `python -m unittest discover -s tests -v`. The offline HTTP tests assert that `/chat` accepts an optional `session_id`, returns the exact Project 1-required fields, echoes a supplied session ID, and adds `agent` to sub-agent tool calls. They do not verify live model correctness or Cloud Run availability.

## Preserve the local comparison checkpoint

Previously recorded genuine model responses on the user's computer are stored in `reports/sample_comparisons.json` and are **not** automatically present in this updated ZIP. If that file contains GPT results, archive it outside the active `reports/sample_comparisons.json` path; run the three actual Gemini baselines and agents before submitting the README. Never relabel GPT results as Gemini results.
