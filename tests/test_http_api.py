"""HTTP contract tests; no actual LLM network call is performed."""
from __future__ import annotations

import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import Handler


class MockReport:
    def to_dict(self):
        return {"response": "Offline mock only [PARKS]", "answer": "Offline mock only [PARKS]",
                "citations": [{"id": "PARKS", "title": "Parks", "url": "https://example.invalid"}],
                "tool_calls": [{"agent": "researcher_parks", "name": "query_parks", "args": {}, "arguments": {}, "result": {}, "round": 1}],
                "agent_trace": [{"agent": "lead", "action": "plan"}], "clarification_needed": False}


class TestHTTPAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request(self, route, body=None):
        req = Request(f"http://127.0.0.1:{self.port}{route}",
                      data=json.dumps(body).encode() if body is not None else None,
                      headers={"Content-Type": "application/json"} if body is not None else {})
        with urlopen(req,timeout=4) as response:
            return response.status,json.loads(response.read())

    def test_health_data_available(self):
        status,result=self.request('/health')
        self.assertEqual(status,200)
        self.assertIn('data_sources_ok',result)

    def test_chat_reports_missing_key(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(HTTPError) as context:
                self.request('/chat',{'message':'Compare ZIP 10001 and ZIP 10002'})
            self.assertEqual(context.exception.code,503)
            payload = json.loads(context.exception.read().decode('utf-8'))
            self.assertIn('response', payload)
            self.assertIn('session_id', payload)
            self.assertEqual(payload['tool_calls'], [])

    def test_chat_response_has_agent_tool_calls(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'offline-mock-only'}):
            with patch('app.PawCityResearch') as research:
                research.return_value.run.return_value=MockReport()
                status,data=self.request('/chat',{'message':'Compare ZIP 10001 and ZIP 10002'})
        self.assertEqual(status,200)
        self.assertEqual(data['tool_calls'][0]['agent'],'researcher_parks')
        self.assertIn('args', data['tool_calls'][0])
        self.assertEqual(data['agent_trace'][0]['agent'],'lead')
        self.assertTrue(data['citations'])
        self.assertEqual(set(('response', 'session_id', 'tool_calls')) - set(data), set())
        self.assertIsInstance(data['session_id'], str)
        self.assertTrue(data['session_id'])

    def test_project1_final_response_contract(self):
        # The final GradPath app(5).py defines these three required properties.
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'offline-mock-only'}):
            with patch('app.PawCityResearch') as research:
                research.return_value.run.return_value = MockReport()
                status, data = self.request('/chat', {'message': 'Compare ZIP 10001 with ZIP 10002'})
        self.assertEqual(status, 200)
        self.assertIsInstance(data['response'], str)
        self.assertIsInstance(data['session_id'], str)
        self.assertIsInstance(data['tool_calls'], list)
        self.assertTrue(all({'name', 'args', 'result', 'agent'} <= set(call) for call in data['tool_calls']))

    def test_chat_echoes_provided_session_id(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'offline-mock-only'}):
            with patch('app.PawCityResearch') as research:
                research.return_value.run.return_value = MockReport()
                status, data = self.request('/chat', {
                    'message': 'Compare ZIP 10001 and ZIP 10002',
                    'session_id': 'existing-project1-session',
                })
        self.assertEqual(status, 200)
        self.assertEqual(data['session_id'], 'existing-project1-session')


if __name__ == '__main__': unittest.main()
