import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import app
import review
from readings import validate

BASELINE = ['T04-NORMAL-D1-A', 'T04-NORMAL-D1-B']
FAILURES = ['T04-TIMEOUT', 'T04-AUTH-401', 'T04-RATE-429', 'T04-OFFLINE', 'T04-SCHEMA-BREAK']


class ReviewTests(unittest.TestCase):
    def test_official_hashes(self):
        result = review.verify_package()
        self.assertTrue(result['verified'])
        self.assertEqual(len(result['files']), 17)

    def test_every_scenario_matches_official_commonjs_adapter(self):
        scenarios = [BASELINE + ['T04-NORMAL-D2'],
                     *[BASELINE + [f] for f in FAILURES],
                     BASELINE + ['T04-TIMEOUT', 'T04-RECOVER-D2', 'T04-RECOVER-D2'],
                     BASELINE + ['T04-NORMAL-D1-B', 'T04-NORMAL-D1-B']]
        adapter = str(review.PACKAGE / 'adapter-reset.example.js')
        fixtures = json.dumps(review.FIXTURES, ensure_ascii=False)
        script = 'const a=require(process.argv[1]); const input=JSON.parse(require("fs").readFileSync(0,"utf8")); console.log(JSON.stringify(input.scenarios.map(ids=>ids.reduce((s,id)=>a.runFixture(s,input.fixtures[id]),a.resetEvaluationState()))));'
        oracle = json.loads(subprocess.check_output(['node', '-e', script, adapter], input=json.dumps({'scenarios': scenarios, 'fixtures': json.loads(fixtures)}).encode('utf-8')))
        for ids, expected in zip(scenarios, oracle):
            state = review.reset()
            for fixture_id in ids:
                state = review.run(state, fixture_id)
            self.assertEqual(state, expected, ids)

    def test_replay_endpoint_never_writes_live_db(self):
        with patch.object(app.storage, 'save', side_effect=AssertionError('live DB touched')):
            client = TestClient(app.app)
            for failure in FAILURES:
                body = client.post('/api/review/replay', json={'fixture_ids': BASELINE + [failure]}).json()
                self.assertTrue(all(c['passed'] for c in body['checks']))
                self.assertEqual(body['state']['current_reading']['normalized_value'], 105)
                self.assertEqual(len(body['state']['daily_readings']), 1)
            body = client.post('/api/review/replay', json={'fixture_ids': BASELINE + ['T04-TIMEOUT', 'T04-RECOVER-D2', 'T04-RECOVER-D2']}).json()
            self.assertEqual(body['state']['status'], {'freshness': 'fresh', 'error_code': 'none'})
            self.assertEqual(body['state']['last_delta'], 15)
            self.assertEqual(len(body['state']['daily_readings']), 2)
            self.assertTrue(all(c['passed'] for c in body['checks']))
            self.assertEqual(client.post('/api/review/replay', json={'fixture_ids': []}).json()['state']['daily_readings'], [])

    def test_invalid_fixture_rejected(self):
        self.assertEqual(TestClient(app.app).post('/api/review/replay', json={'fixture_ids': ['../../.env']}).status_code, 400)

    def test_kst_boundary_and_schema_validation(self):
        reading = dict(review.FIXTURES['T04-NORMAL-D1-A']['payload'])
        reading['fetched_at'] = '2026-08-23T15:00:00Z'
        self.assertTrue(validate(reading))
        reading['record_date'] = '2026-08-23'
        with self.assertRaises(ValueError):
            validate(reading)

    def test_review_routes(self):
        client = TestClient(app.app)
        for path in ['/review', '/assets/review.js', '/assets/review.css', '/assets/t04/fixtures/recover-d2.json']:
            self.assertEqual(client.get(path).status_code, 200, path)
