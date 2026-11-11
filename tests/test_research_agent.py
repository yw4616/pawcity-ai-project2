"""Tests the agent shape with a strictly labeled offline mock, not a real LLM."""
import csv
import json
import tempfile
import threading
import unittest
from pathlib import Path
from pawcity.research_agent import DataTools, PawCityResearch, known_nyc_zip, screen_for_clarification


def save_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


class FakeModel:
    def __init__(self):
        self.roles = []
        self.lock = threading.Lock()

    def __call__(self, role, instructions, content):
        with self.lock:
            self.roles.append(role)
        if role == 'lead' and 'checking research coverage' not in instructions:
            return json.dumps({'clarification':None, 'domains':['parks','licenses','barking'], 'focus':'Comparison'})
        if role == 'lead':
            return json.dumps({'needs_followup':True, 'follow_up_domains':['bites'], 'reason':'Missing bite data'})
        if role == 'writer':
            return 'Evidence: [PARKS], [LICENSES_2026], [BARKING_2025], [BITES_2025]. Safety cannot be determined.'
        return f'Offline mock summary from {role}'


class TestResearchAgent(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        save_csv(self.root/'data/processed/zip_summary.csv',
                 ['zip_code','dog_runs','license_periods','dog_related_311','reported_bites','documented_breeds'],
                 [{'zip_code':'10001','dog_runs':1,'license_periods':3,'dog_related_311':4,'reported_bites':1,'documented_breeds':2},
                  {'zip_code':'10002','dog_runs':1,'license_periods':4,'dog_related_311':5,'reported_bites':2,'documented_breeds':2},
                  {'zip_code':'90001','dog_runs':0,'license_periods':3,'dog_related_311':0,'reported_bites':0,'documented_breeds':1}])
        save_csv(self.root/'data/raw/dog_runs.csv', ['objectid','name','zipcode'],
                 [{'objectid':'1','name':'Mock Facility','zipcode':'10001, 10002'}])
        for name, fields, rows in [
            ('dog_licenses',['zipcode','breedname','license_periods'],[{'zipcode':'10001','breedname':'Samoyed','license_periods':3}]),
            ('dog_311',['incident_zip','complaint_type','descriptor','reports'],[{'incident_zip':'10001','complaint_type':'Noise','descriptor':'Noise, Barking Dog (NR5)','reports':4}]),
            ('dog_bites',['zipcode','bite_reports'],[{'zipcode':'10001','bite_reports':1}])]:
            save_csv(self.root/'data/raw'/f'{name}.csv',fields,rows)
        log = {'dog_runs':{'status':'ok','rows':1},
               'dog_licenses':{'status':'ok','rows':1,'license_extract_year':'2026'},
               'dog_311':{'status':'ok','rows':1,'event_year':2025,
                          'complaint_scope':"Only descriptor = 'Noise, Barking Dog (NR5)', NOT all dog complaints"},
               'dog_bites':{'status':'ok','rows':1,'event_year':2025}}
        (self.root/'data/metadata').mkdir(parents=True,exist_ok=True)
        (self.root/'data/metadata/query_log.json').write_text(json.dumps(log),encoding='utf-8')

    def tearDown(self):
        self.folder.cleanup()

    def test_park_matches_multi_zip_facility(self):
        output=DataTools(self.root).query('parks',['10001','10002'])
        self.assertEqual([r['facility_match_count'] for r in output['rows']],[1,1])

    def test_scope_and_source_citation(self):
        data=DataTools(self.root).query('barking',['10001'])
        self.assertEqual(data['source_id'],'BARKING_2025')
        self.assertIn('Barking Dog',data['coverage']['complaint_scope'])

    def test_missing_zip_is_null_not_zero(self):
        self.assertIsNone(DataTools(self.root).query('bites',['88888'])['rows'][0]['value'])

    def test_missing_source_fails_closed(self):
        path=self.root/'data/metadata/query_log.json'
        log=json.loads(path.read_text())
        log['dog_311']={'status':'error'}
        path.write_text(json.dumps(log))
        with self.assertRaises(RuntimeError):DataTools(self.root)

    def test_clarification(self):
        self.assertIsNotNone(screen_for_clarification('good for dogs?'))
        self.assertIsNotNone(screen_for_clarification('Is Williamsburg good for large dogs?'))

    def test_conservative_zip_scope(self):
        self.assertTrue(known_nyc_zip('11211'))
        self.assertFalse(known_nyc_zip('90001'))

    def test_parallel_research_and_gap_followup(self):
        fake=FakeModel()
        result=PawCityResearch(self.root, llm=fake,max_turns=2).run('Compare dog services in ZIP 10001 and ZIP 10002')
        self.assertEqual(len(result.tool_calls),4)
        self.assertEqual({t['agent'] for t in result.tool_calls},
                         {'researcher_parks','researcher_licenses','researcher_barking','researcher_bites'})
        self.assertTrue(any(x.get('action')=='gap_review' for x in result.agent_trace))
        self.assertIn('[BARKING_2025]',result.answer)
        self.assertIn('response',result.to_dict())
        self.assertFalse(result.clarification_needed)

    def test_no_llm_calls_on_vague_query(self):
        fake=FakeModel()
        result=PawCityResearch(self.root, llm=fake).run('good for dogs?')
        self.assertTrue(result.clarification_needed)
        self.assertFalse(fake.roles)


if __name__=='__main__': unittest.main()
