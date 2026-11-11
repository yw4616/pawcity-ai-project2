"""Offline tests for model 429 handling and checkpointed comparisons."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from pawcity import research_agent as ra
from scripts import compare_samples as cmp


class ModelRetryTests(unittest.TestCase):
    def _model(self):
        model = object.__new__(ra.APIModel)
        model.api_key = "fake-unit-test-key"
        model.api_url = "https://api.example.invalid/v1/responses"
        model.model = "test-model"
        return model

    def test_429_retries_then_succeeds(self):
        err = HTTPError(
            "https://api.example.invalid/v1/responses", 429, "Too Many Requests",
            {"Retry-After": "0"},
            io.BytesIO(b'{"error":{"message":"Rate limit. Please try again in 1s."}}'),
        )

        class GoodResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return json.dumps({"output": [{"content": [
                    {"type": "output_text", "text": "Success"}
                ]}]}).encode("utf-8")

        with patch.object(ra, "pace_api_request"), patch.object(ra.time, "sleep") as sleep, \
             patch.object(ra, "urlopen", side_effect=[err, GoodResponse()]) as call:
            result = self._model().request("Hello")
            self.assertEqual(result, "Success")
            self.assertEqual(call.call_count, 2)
            self.assertTrue(sleep.called)

    def test_insufficient_quota_does_not_retry(self):
        err = HTTPError(
            "https://api.example.invalid/v1/responses", 429, "No credits", {},
            io.BytesIO(b'{"error":{"type":"insufficient_quota"}}'),
        )
        with patch.object(ra, "pace_api_request"), patch.object(ra, "urlopen", side_effect=err) as call:
            with self.assertRaisesRegex(RuntimeError, "no remaining credits"):
                self._model().request("Hello")
            self.assertEqual(call.call_count, 1)


class CheckpointComparisonTests(unittest.TestCase):
    def test_resume_does_not_repeat_completed_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "Intro\n<!-- COMPARISON_RESULTS_START -->\nplaceholder\n"
                "<!-- COMPARISON_RESULTS_END -->\n", encoding="utf-8"
            )
            samples = [
                {"id": "one", "question": "Question one?", "source": "data.csv", "expected": "one"},
                {"id": "two", "question": "Question two?", "source": "data.csv", "expected": "two"},
            ]
            counts = {"baselines": 0, "agents": 0}

            class FakeModel:
                model = "test-model"
                def request(self, question, instructions=None):
                    counts["baselines"] += 1
                    return "Baseline " + question

            class FakeResult:
                def to_dict(self):
                    return {"response": "Agent answer", "tool_calls": [{"agent": "researcher_parks"}],
                            "citations": [{"id": "PARKS"}]}

            class FakeAgent:
                def __init__(self, *args, **kwargs):
                    pass
                def run(self, question):
                    counts["agents"] += 1
                    if counts["agents"] == 2:
                        raise RuntimeError("Simulated API rate limit")
                    return FakeResult()

            with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-unit-test-key"}), \
                 patch.object(cmp, "ROOT", root), \
                 patch.object(cmp, "SAMPLES", samples), \
                 patch.object(cmp, "APIModel", FakeModel), \
                 patch.object(cmp, "PawCityResearch", FakeAgent):
                with self.assertRaisesRegex(RuntimeError, "rate limit"):
                    cmp.main()
                partial = json.loads((root / "reports/sample_comparisons.json").read_text())
                self.assertEqual(len(partial["comparisons"]), 2)
                self.assertIn("agent_answer", partial["comparisons"][0])
                self.assertIn("same_model_no_system_no_tools_answer", partial["comparisons"][1])
                self.assertNotIn("agent_answer", partial["comparisons"][1])
                cmp.main()
                self.assertEqual(counts["baselines"], 2)
                self.assertEqual(counts["agents"], 3)
                self.assertIn("Agent answer", (root / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
