# Running PawCity in JupyterLab

This single, fully English notebook replaces the earlier Step 2 / Step 2B / Step 3 fragments.

1. Unzip the project and keep its folder intact; do not move individual Python files.
2. Open JupyterLab and navigate to `PawCity_AI_Complete`.
3. Open `PawCity_Complete.ipynb`.
4. Select a Python 3.11+ kernel and run cells top-to-bottom with **Shift + Enter**.
5. All four official-source snapshots are included; you do not have to download them again.
6. The data verification, query examples and offline tests run without any API key.
7. Live Research requires `OPENAI_API_KEY` in the environment. Do not paste it into saved cells or commit it to GitHub. The optional live-model cell skips itself when the key is missing.
8. To view the website, open a terminal in the project directory and run `python app.py`, then navigate to `http://localhost:8080`.

If Python says `ModuleNotFoundError: pawcity`, make sure the notebook is in the same folder as `app.py` and the `pawcity/` directory. If the data quality report shows a failed source, do not substitute zeros. See `DATA_DICTIONARY.md` and the provenance log.

After successful offline steps, the next user actions are: configure a model API key, run actual model-based comparisons, align `/chat` with the exact Project 1 starter if provided, and deploy to Cloud Run with GitHub continuous deployment. These actions are not silently completed by the notebook.

## Rate limits and resumable comparisons

The comparison workflow has automatic model-request pacing and saves progress after each baseline and complete agent response. At low usage tiers, `PAWCITY_API_RPM=7` conservatively stays below a 10 requests/minute quota. The run may take several minutes.

Run in a Jupyter cell with `OPENAI_API_KEY` already configured:

```python
import os, runpy
os.environ["PAWCITY_API_RPM"] = "7"
runpy.run_path(str(ROOT / "scripts" / "compare_samples.py"), run_name="__main__")
```

If interrupted, run that same cell again. Previously saved results in `reports/sample_comparisons.json` will be reused. Never commit API keys to GitHub.
