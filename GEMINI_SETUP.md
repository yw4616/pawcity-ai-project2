# PawCity AI — Gemini on Google Cloud Vertex AI

## Why this migration

This implementation replaces the former direct OpenAI Responses API with Google Cloud Vertex AI Gemini. It preserves the same four local NYC Open Data sources, Lead → independent parallel Researchers → Lead gap review → Writer flow, citations, and Project 1 `/chat` response contract.

**Model:** `gemini-3.5-flash-lite` (configurable with `PAWCITY_MODEL`).
**Vertex location:** `global` by default. Verify this model is accessible to the school GCP project.
**Billing:** Google Cloud project billing. Eligible school-provided credits may offset usage, depending on the credit terms. No OpenAI API key or independent Gemini Developer API key is needed.

## 1. Configure the school GCP project

In Google Cloud Console choose your course project. Copy its **Project ID** (not its display name, number, or OpenAI Project ID). Ensure that billing is enabled and the Vertex AI API (`aiplatform.googleapis.com`) is enabled. Ensure your account can use Vertex AI models (e.g. `roles/aiplatform.user`).

```bash
# Install the Google Cloud CLI first if the gcloud command is unavailable.
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_SCHOOL_GCP_PROJECT_ID
gcloud auth application-default set-quota-project YOUR_SCHOOL_GCP_PROJECT_ID
```

Run the app from the repository directory:

```bash
export GOOGLE_CLOUD_PROJECT="YOUR_SCHOOL_GCP_PROJECT_ID"
export GOOGLE_CLOUD_LOCATION="global"
export PAWCITY_MODEL="gemini-3.5-flash-lite"
export PAWCITY_MAX_TURNS="2"
python app.py
```

For Jupyter, open `PawCity_Gemini_Check.ipynb`. It sets the same variables in the notebook process and makes one small real model call. The model access test incurs billable Google Cloud usage.

## 2. Verify the end-to-end research path

```bash
python -m unittest discover -s tests -v
```

For actual Gemini evaluation, use Jupyter (`PawCity_Gemini_Check.ipynb` and `PawCity_Resume_Comparisons.ipynb`) or run:

```bash
export GOOGLE_CLOUD_PROJECT="YOUR_SCHOOL_GCP_PROJECT_ID"
python scripts/compare_samples.py
```

The same Gemini model generates each bare question answer **without tools and without system instructions** and each tool-assisted PawCity answer. Each completed result is checkpointed. A previous `gpt-4.1-mini` checkpoint is **not reusable**. Keep the original outside the active comparison path as an archive, then generate the actual Gemini responses. Do not invent responses.

## 3. Cloud Run from GitHub

Follow the instructor's continuous deploy guide and choose the Dockerfile build. Cloud Run uses the **runtime service account identity**, not the developer's local `gcloud` login.

- Set Cloud Run environment variables: `GOOGLE_CLOUD_PROJECT=YOUR_SCHOOL_GCP_PROJECT_ID`, `GOOGLE_CLOUD_LOCATION=global`, `PAWCITY_MODEL=gemini-3.5-flash-lite`, `PAWCITY_MAX_TURNS=2`, `PAWCITY_API_RPM=7`.
- Enable `aiplatform.googleapis.com` on that GCP project.
- Grant the **Cloud Run runtime service account** the project IAM role `roles/aiplatform.user`; do not give a service account user-key JSON to the app.
- Set request timeout to 300 seconds, limit concurrency/max instances if API quota requires, and apply the instructor's Columbia IAP policy if deploying under the Columbia organization.
- Cloud Run's metadata server supplies temporary OAuth access tokens. This project does not need `OPENAI_API_KEY` and does not need a stored Gemini API key.
- Verify both `/health` and a real `/chat` response through the configured access policy. `/health` reporting `model_configured: true` means the project ID is present, **not** that permissions or quotas were verified.

## 4. Troubleshooting

| Symptom | Check |
|---|---|
| `gcloud` not found | Install Google Cloud CLI and open a new Terminal |
| Local credentials unavailable | Run `gcloud auth application-default login` |
| HTTP 403 | Check school project ID, Vertex AI API, billing, service identity and `roles/aiplatform.user` |
| HTTP 404 | Check model ID and whether the model is available to your project/location |
| HTTP 429 | Check Google Cloud model quotas; rerun the checkpointed comparison later |
| Missing `GOOGLE_CLOUD_PROJECT` | Set the actual GCP project ID locally and as a Cloud Run environment variable |
| Old GPT results prevent comparison | Archive `reports/sample_comparisons.json` and rerun all three questions with Gemini |

**Important:** The offline tests verify code paths using mocks. A real Vertex AI call and Cloud Run deployment require your own authorized Google Cloud project and cannot be certified by offline tests alone.
