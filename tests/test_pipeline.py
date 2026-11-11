"""Repeatable no-network tests for ZIP handling and data completeness."""
import tempfile
import unittest
from pathlib import Path
from pawcity.pipeline import normalize_zip,parse_zip_tags,zip_summary,write_csv


class TestZipNormalization(unittest.TestCase):
    def test_zip_five_digit(self):
        self.assertEqual(normalize_zip('10024'),'10024')
        self.assertEqual(normalize_zip(11211),'11211')
        self.assertEqual(normalize_zip('11211.0'),'11211')

    def test_reject_bad_zips(self):
        for value in (None,'','00000','11211-1234','Brooklyn','123'):
            self.assertIsNone(normalize_zip(value))

    def test_multi_zip(self):
        self.assertEqual(parse_zip_tags('10459, 10472'),['10459','10472'])
        self.assertEqual(parse_zip_tags('10459;10459'),['10459'])


class TestSummary(unittest.TestCase):
    def test_aggregated_sources_and_multi_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)
            write_csv(raw/'dog_runs.csv',[{'zipcode':'10024, 10025','name':'Run A'}],['zipcode','name'])
            write_csv(raw/'dog_licenses.csv',[{'zipcode':'10024','breedname':'Samoyed','license_periods':'5'}],
                      ['zipcode','breedname','license_periods'])
            write_csv(raw/'dog_311.csv',[{'incident_zip':'10024','reports':'3'}],['incident_zip','reports'])
            write_csv(raw/'dog_bites.csv',[{'zipcode':'10024','bite_reports':'1'}],['zipcode','bite_reports'])
            rows,meta=zip_summary(raw)
            by_zip={r['zip_code']:r for r in rows}
            self.assertEqual(by_zip['10024']['dog_runs'],1)
            self.assertEqual(by_zip['10025']['dog_runs'],1)
            self.assertEqual(by_zip['10024']['license_periods'],5)
            self.assertEqual(meta['multi_zip_facility_records'],1)

    def test_unavailable_source_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)
            write_csv(raw/'dog_runs.csv',[{'zipcode':'10024'}],['zipcode'])
            write_csv(raw/'dog_311.csv',[{'incident_zip':'10024','reports':'4'}],['incident_zip','reports'])
            rows,meta=zip_summary(raw,statuses={'dog_runs':{'status':'ok'},'dog_311':{'status':'error'}})
            self.assertEqual(rows[0]['dog_related_311'],'')
            self.assertEqual(meta['available_sources'],['dog_runs'])


if __name__=='__main__': unittest.main()
