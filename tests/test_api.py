import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app
from parking import SourceError

class APITests(unittest.TestCase):
    def test_no_secret_in_configuration(self):
        with patch.dict(os.environ, {'DAEJEON_PARKING_API_KEY':'SYNTHETIC_SECRET','DATABASE_URL':'SYNTHETIC_DB'}):
            response=TestClient(app.app).get('/api/config')
            self.assertNotIn('SYNTHETIC_SECRET',response.text)
            self.assertNotIn('SYNTHETIC_DB',response.text)

    def test_failed_refresh_preserves_snapshot(self):
        prior={'items':[{'id':'synthetic','available':12}], 'fetched_at':'2030-01-01T00:00:00+09:00'}
        # 古い日付にして必ず cache refresh を通す。
        prior['fetched_at']='2000-01-01T00:00:00+09:00'
        with patch.dict(os.environ, {'DAEJEON_PARKING_API_KEY':'SYNTHETIC_SECRET'}),patch.object(app.storage,'latest',return_value=prior),patch.object(app,'fetch_page',AsyncMock(side_effect=SourceError('denied'))):
            response=TestClient(app.app).get('/api/parking').json()
            self.assertEqual(response['items'][0]['available'],12)
            self.assertEqual(response['state'],'stale')
            self.assertEqual(response['error_code'],'denied')

    def test_frontend_and_assets(self):
        client=TestClient(app.app)
        for path in ['/','/assets/app.js','/assets/style.css']:
            self.assertEqual(client.get(path).status_code,200)

if __name__=='__main__':unittest.main()
