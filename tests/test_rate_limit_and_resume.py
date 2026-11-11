"""Offline tests for model 429 handling and checkpointed comparisons."""
from __future__ import annotations

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
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "offline-test-project"}):
            return ra.GeminiModel(model="offline-test-model")

    def test_429_retries_then_succeeds(self):
        err = HTTPError("https://example.invalid", 429, "Too Many Requests", {}, None)
        model = self._model()
        with patch.object(ra, "pace_api_request"), patch.object(ra.time, "sleep") as sleep, \
             patch.object(model, "_generate_once", side_effect=[err, "Success"]) as call:
            self.assertEqual(model.request("Hello"), "Success")
            self.assertEqual(call.call_count, 2)
            self.assertTrue(sleep.called)

    def test_401_is_not_retried(self):
        err = HTTPError("https://example.invalid", 401, "Unauthorized", {}, None)
        model = self._model()
        with patch.object(ra, "pace_api_request"), \
             patch.object(model, "_generate_once", side_effect=err) as call:
            with self.assertRaisesRegex(RuntimeError, "Vertex AI Gemini HTTP 401"):
                model.request("Hello")
            self.assertEqual(call.call_count, 1)

    def test_no_system_instruction_for_baseline(self):
        model = self._model()
        with patch.object(ra, "pace_api_request"), \
             patch.object(model, "_generate_once", return_value="Response") as call:
            model.request("Question", instructions=None)
            call.assert_called_once_with("Question", None)

    def test_vertex_request_payload_and_context(self):
        model = self._model()
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self):
                return json.dumps({"candidates": [{"content": {"parts": [{"text": "Confirmed"}]}}]}).encode()
        with patch.object(ra, "google_access_token", return_value="test-access-token"), \
             patch.object(ra, "urlopen", return_value=FakeResponse()) as urlopen:
            self.assertEqual(model._generate_once("Q", None), "Confirmed")
            req = urlopen.call_args.args[0]
            self.assertIn("offline-test-model", req.full_url)
            self.assertIn("offline-test-project", req.full_url)
            self.assertNotIn("systemInstruction", json.loads(req.data))
            self.assertIn("Authorization", req.headers)
            self.assertNotIn("OPENAI", str(req.headers))

    def test_vertex_researcher_system_instruction(self):
        model = self._model()
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self):
                return json.dumps({"candidates": [{"content": {"parts": [{"text": "Confirmed"}]}}]}).encode()
        with patch.object(ra, "google_access_token", return_value="test-access-token"), \
             patch.object(ra, "urlopen", return_value=FakeResponse()) as urlopen:
            model._generate_once("Q", "Independent researcher")
            self.assertIn("systemInstruction", json.loads(urlopen.call_args.args[0].data))


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

            with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "offline-test-project"}), \
                 patch.object(cmp, "ROOT", root), \
                 patch.object(cmp, "SAMPLES", samples), \
                 patch.object(cmp, "GeminiModel", FakeModel), \
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
