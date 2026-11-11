"""Verify monthly 311 aggregation without accessing the network."""
import unittest
from unittest.mock import patch
from scripts.download_data import fetch


class TestDownload(unittest.TestCase):
    def test_311_monthly_merge(self):
        def fake_request(dataset,params,timeout):
            self.assertEqual(dataset,'dog_311')
            return ([{'incident_zip':'10001','reports':'2'}], 'https://example.invalid/monthly')
        with patch('scripts.download_data.request',side_effect=fake_request):
            rows,columns,meta=fetch('dog_311',2025,30)
        self.assertEqual(rows[0]['reports'],24)
        self.assertEqual(meta['monthly_counts']['12'],2)
        self.assertEqual(len(meta['api_query_urls']),12)
        self.assertEqual(meta['event_year'],2025)


if __name__=='__main__': unittest.main()
