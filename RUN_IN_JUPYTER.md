# Running PawCity in JupyterLab

This single, fully English notebook replaces the earlier Step 2 / Step 2B / Step 3 fragments.

1. Unzip the project and keep its folder intact; do not move individual Python files.
2. Open JupyterLab and navigate to the extracted `PawCity_AI_Gemini_VertexAI` folder.
3. Open `PawCity_Complete.ipynb`.
4. Select a Python 3.11+ kernel and run cells top-to-bottom with **Shift + Enter**.
5. All four official-source snapshots are included; you do not have to download them again.
6. The data verification, query examples and offline tests run without any API key.
7. Live Research requires the school `GOOGLE_CLOUD_PROJECT`, enabled Vertex AI API, and local Google Cloud ADC (`gcloud auth application-default login`). Never paste or commit an access token or API key.
8. To view the website, open a terminal in the project directory and run `python app.py`, then navigate to `http://localhost:8080`.

If Python says `ModuleNotFoundError: pawcity`, make sure the notebook is in the same folder as `app.py` and the `pawcity/` directory. If the data quality report shows a failed source, do not substitute zeros. See `DATA_DICTIONARY.md` and the provenance log.

After successful offline steps, the next user actions are: configure Google Cloud credentials and the Vertex AI project, run Gemini model comparisons, and deploy to Cloud Run with GitHub continuous deployment. These actions are not silently completed by the notebook.

## Rate limits and resumable comparisons

The comparison workflow has automatic model-request pacing and saves progress after each baseline and complete agent response. At low usage tiers, `PAWCITY_API_RPM=7` conservatively stays below a 10 requests/minute quota. The run may take several minutes.

Run in a Jupyter cell after authenticating with `gcloud auth application-default login` and configuring the school GCP project:

```python
import os, runpy
os.environ["PAWCITY_API_RPM"] = "7"
os.environ["GOOGLE_CLOUD_PROJECT"] = "YOUR_SCHOOL_GCP_PROJECT_ID"
os.environ["PAWCITY_MODEL"] = "gemini-3.5-flash-lite"
runpy.run_path(str(ROOT / "scripts" / "compare_samples.py"), run_name="__main__")
```

If interrupted, run that same cell again. Previously saved results in `reports/sample_comparisons.json` will be reused. Never commit access tokens or secret keys to GitHub. Do not reuse GPT model comparisons as Gemini results.
