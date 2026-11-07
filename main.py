"""Local agent context observability. Run: python main.py"""
import argparse
import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
DB = ROOT / "memory.db"
CATEGORIES = ("system", "conversation", "working", "retrieved", "tools")


def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def initialize():
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS workspaces (id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE)")
        db.execute("INSERT OR IGNORE INTO workspaces (id, name) VALUES (1, 'My workspace')")
        db.execute("""CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, session TEXT NOT NULL, agent TEXT NOT NULL,
            model TEXT NOT NULL, timestamp TEXT NOT NULL, capacity INTEGER NOT NULL,
            system INTEGER NOT NULL, conversation INTEGER NOT NULL,
            working INTEGER NOT NULL, retrieved INTEGER NOT NULL, tools INTEGER NOT NULL,
            input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
            input_rate REAL NOT NULL, output_rate REAL NOT NULL, demo INTEGER NOT NULL DEFAULT 0)""")
        if 'workspace' not in [row['name'] for row in db.execute('PRAGMA table_info(events)')]:
            db.execute('ALTER TABLE events ADD COLUMN workspace INTEGER NOT NULL DEFAULT 1')
        db.execute('CREATE INDEX IF NOT EXISTS events_workspace ON events(workspace, id)')


def workspace_id(value=1):
    if type(value) is not int or value < 1:
        raise ValueError('workspace must be a positive integer ID')
    with connect() as db:
        if not db.execute('SELECT 1 FROM workspaces WHERE id=?', (value,)).fetchone():
            raise ValueError('Workspace does not exist')
    return value


def validate(data):
    if not isinstance(data, dict):
        raise ValueError("Event must be a JSON object")
    result = {}
    result['workspace'] = workspace_id(data.get('workspace', 1))
    for key in ("session", "agent", "model"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 160:
            raise ValueError(key + " must be a non-empty string of at most 160 characters")
        result[key] = value.strip()
    for key in ("capacity",) + CATEGORIES + ("input_tokens", "output_tokens"):
        value = data.get(key, 0)
        if type(value) is not int or value < 0 or value > 1_000_000_000:
            raise ValueError(key + " must be a non-negative integer up to 1 billion")
        result[key] = value
    if result["capacity"] == 0:
        raise ValueError("capacity must be greater than zero")
    for key in ("input_rate", "output_rate"):
        value = data.get(key, 0)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1_000_000:
            raise ValueError(key + " must be a finite non-negative USD price per million tokens")
        result[key] = value
    result["timestamp"] = datetime.now(timezone.utc).isoformat()
    return result


def insert(db, event, demo=0):
    event = dict(event, demo=demo)
    keys = list(event)
    cursor = db.execute("INSERT INTO events (" + ",".join(keys) + ") VALUES (" + ",".join("?" for _ in keys) + ")", list(event.values()))
    return cursor.lastrowid


def seed(workspace=1):
    workspace_id(workspace)
    with connect() as db:
        if db.execute("SELECT 1 FROM events WHERE demo=1 AND workspace=? LIMIT 1", (workspace,)).fetchone():
            return
        names = [("research-01", "Research agent", "General model", 128000),
                 ("builder-02", "Code agent", "Code model", 128000),
                 ("support-03", "Support agent", "Fast model", 32000)]
        now = datetime.now(timezone.utc)
        for step in range(24):
            for i, (session, agent, model, capacity) in enumerate(names):
                event = validate(dict(workspace=workspace, session=session, agent=agent, model=model, capacity=capacity,
                    system=2400, conversation=int(capacity * (.08 + step * .008)),
                    working=int(capacity * (.06 + step * .004 + i * .015)),
                    retrieved=int(capacity * (.05 + step * .003)), tools=1200 + step * 190,
                    input_tokens=2800 + step * 320, output_tokens=400 + step * 34,
                    input_rate=2.5, output_rate=10))
                event["timestamp"] = (now - timedelta(minutes=(23-step)*5)).isoformat()
                insert(db, event, demo=1)


def snapshot(workspace=1):
    workspace_id(workspace)
    with connect() as db:
        rows = [dict(row) for row in db.execute("SELECT * FROM events WHERE workspace=? ORDER BY id", (workspace,))]
    for row in rows:
        row["used"] = sum(row[key] for key in CATEGORIES)
        row["cost"] = (row["input_tokens"] * row["input_rate"] + row["output_tokens"] * row["output_rate"]) / 1_000_000
    return {"events": rows, "categories": CATEGORIES}


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, content_type="application/json"):
        if content_type == "application/json":
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path)
        if path.path == '/api/workspaces':
            with connect() as db:
                workspaces = [dict(row) for row in db.execute('SELECT * FROM workspaces ORDER BY id')]
            self.respond(200, {'workspaces': workspaces})
        elif path.path == "/api/events":
            try:
                workspace = int(parse_qs(path.query).get('workspace', ['1'])[0])
                self.respond(200, snapshot(workspace))
            except ValueError as error:
                self.respond(400, {'error': str(error)})
        elif self.path == '/netrootai-logo.png':
            self.respond(200, (ROOT / 'static' / 'netrootai-logo.png').read_bytes(), 'image/png')
        elif self.path in ("/", "/app.js", "/style.css"):
            name = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[self.path]
            mime = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript", "style.css": "text/css"}[name]
            self.respond(200, (ROOT / "static" / name).read_bytes(), mime)
        else:
            self.respond(404, {"error": "Not found"})

    def do_POST(self):
        if self.path not in ("/api/events", "/api/demo", '/api/workspaces'):
            return self.respond(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 65536:
                raise ValueError("Body must be at most 64 KB")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('Body must be a JSON object')
            if self.path == '/api/workspaces':
                name = payload.get('name')
                if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60:
                    raise ValueError('Name must contain 1–60 characters')
                try:
                    with connect() as db:
                        cursor = db.execute('INSERT INTO workspaces (name) VALUES (?)', (name.strip(),))
                        created = {'id': cursor.lastrowid, 'name': name.strip()}
                except sqlite3.IntegrityError:
                    return self.respond(409, {'error': 'A workspace with this name already exists'})
                return self.respond(201, created)
            if self.path == "/api/demo":
                seed(workspace_id(payload.get('workspace', 1)))
                return self.respond(200, {"ok": True})
            event = validate(payload)
            with connect() as db:
                event_id = insert(db, event)
            self.respond(201, {"id": event_id})
        except (ValueError, UnicodeDecodeError) as error:
            self.respond(400, {"error": str(error)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    initialize()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("Netroot AI is running at http://127.0.0.1:" + str(args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
