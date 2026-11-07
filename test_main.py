"""Run with: python -m unittest -v"""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import main


class MemoryAPITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = main.DB
        main.DB = Path(self.temp.name) / 'test.db'
        main.initialize()
        self.server = main.ThreadingHTTPServer(('127.0.0.1', 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        main.DB = self.original
        self.temp.cleanup()

    def post(self, path, body):
        return urlopen(Request(self.url + path, json.dumps(body).encode(), {'Content-Type': 'application/json'}))

    def test_ingestion_cost_and_persistence(self):
        with self.post('/api/events', dict(session='s', agent='a', model='m', capacity=100,
                working=80, input_tokens=1000, output_tokens=100, input_rate=2, output_rate=10)) as response:
            self.assertEqual(response.status, 201)
        main.initialize()
        with urlopen(self.url + '/api/events') as response:
            event = json.load(response)['events'][0]
        self.assertEqual(event['used'], 80)
        self.assertAlmostEqual(event['cost'], .003)
        self.assertEqual(event['demo'], 0)

    def test_invalid_values_rejected(self):
        for extra in ({'capacity':0}, {'working':-1}, {'input_rate':float('inf')}, {'tools':True}):
            with self.subTest(extra=extra), self.assertRaises(HTTPError) as error:
                self.post('/api/events', dict(dict(session='s', agent='a', model='m', capacity=100), **extra))
            self.assertEqual(error.exception.code, 400)
        self.assertEqual(main.snapshot()['events'], [])

    def test_workspace_isolation_and_validation(self):
        with self.post('/api/workspaces', {'name': 'Research'}) as response:
            workspace = json.load(response)['id']
        with self.post('/api/events', dict(workspace=workspace, session='s', agent='a', model='m', capacity=100)):
            pass
        self.assertEqual(main.snapshot()['events'], [])
        with urlopen(self.url + '/api/events?workspace=' + str(workspace)) as response:
            self.assertEqual(len(json.load(response)['events']), 1)
        main.seed(workspace)
        main.seed(workspace)
        self.assertEqual(len(main.snapshot(workspace)['events']), 73)
        self.assertEqual(main.snapshot()['events'], [])
        for path, body, status in [('/api/workspaces', {'name':'research'},409),
                ('/api/workspaces', {'name':'  '},400),
                ('/api/events', dict(workspace=999, session='s', agent='a', model='m', capacity=100),400)]:
            with self.assertRaises(HTTPError) as error:
                self.post(path, body)
            self.assertEqual(error.exception.code, status)
        main.initialize()
        with urlopen(self.url + '/api/workspaces') as response:
            self.assertEqual(len(json.load(response)['workspaces']), 2)

    def test_existing_database_migration(self):
        with main.connect() as db:
            db.execute('DROP TABLE events')
            db.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, session TEXT)')
            db.execute("INSERT INTO events (session) VALUES ('old-session')")
        main.initialize()
        main.initialize()
        with main.connect() as db:
            row = db.execute('SELECT session, workspace FROM events').fetchone()
        self.assertEqual(tuple(row), ('old-session', 1))

    def test_demo_is_idempotent_and_assets_load(self):
        for _ in range(2):
            with self.post('/api/demo', {}):
                pass
        self.assertEqual(len(main.snapshot()['events']), 72)
        for asset in ('/', '/app.js', '/style.css'):
            with urlopen(self.url + asset) as response:
                self.assertEqual(response.status, 200)
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + '/../main.py')
        self.assertEqual(error.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
