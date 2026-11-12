<p align="center">
  <img src="static/netrootai-logo.png" alt="Netroot AI logo" width="140">
</p>

# Netroot AI — Agent Memory Observability

Netroot AI is a local observability dashboard for understanding how AI agents use their context windows. Track working memory, conversation history, retrieved context, and tool results alongside estimated model costs across agent sessions and workspaces.

Built with Python’s standard library, SQLite, and plain HTML, CSS, and JavaScript. No third-party Python packages, frontend build step, or cloud account is required.


<img width="1863" height="1020" alt="image" src="https://github.com/user-attachments/assets/650d32db-e8fd-4f82-898e-c3811675a99a" />


## Features

- **Overview dashboard:** tracked sessions, current context tokens, capacity utilization, and estimated USD spend.
- **Memory visualizations:** context usage over time and a breakdown of the latest memory composition.
- **Session monitoring:** agent and model details, context usage, health labels, last-seen timestamps, and cumulative estimated cost.
- **Local workspaces:** create named workspaces and keep their events, demo data, charts, and exports separate.
- **Filtering and export:** select live or demo data, filter by agent, search the session table, and export selected events as JSON.
- **Demo data:** explore three sample agents with 72 events per workspace.
- **Background themes:** switch between black and white backgrounds with blue text and charts. Theme and workspace selections are remembered in the browser.
- **Persistent storage:** retain events and workspaces in a local SQLite database across restarts.

The dashboard polls for updates every five seconds. Agents must submit token metadata through the HTTP API; automatic instrumentation is not included.

## Quick start

Requires **Python 3.9 or later** and a modern browser.

From the project directory, optionally create and activate a virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
```

On Windows, activate with `.venv\Scripts\activate` instead.

Start the application:

```sh
python main.py
```

Open **http://127.0.0.1:8000**. In PyCharm, run `main.py` with the project interpreter.

To choose another port:

```sh
python main.py --port 8080
```

Stop the server with `Ctrl+C`. Restart it after changing backend code.

## Explore the overview

1. Select **My workspace**, or choose **Create workspace** and enter a name.
2. Click **Load demo data** to populate the selected workspace.
3. Set the Data filter to **All data** or **Demo only**.
4. Review usage metrics, the context timeline, memory composition, and agent sessions.
5. Use **Export JSON** to download events matching the workspace, source, and agent filters. Session-table search only filters the table.

Demo sessions represent research, code, and support agents. Loading the demo again does not duplicate its events in that workspace. Demo records are labeled separately from real submissions.

## Understanding the metrics

| Metric | Meaning |
| --- | --- |
| Tracked sessions | Unique agent/session pairs in the selected data, with live and demo records treated separately. |
| Current context | Sum of used tokens from the latest snapshot of each session. |
| Context utilization | Total current context divided by the combined capacity of those latest session snapshots. |
| Estimated spend | Sum of per-event token costs across all selected events. |
| Session health | Healthy below 70% utilization, elevated from 70% to below 90%, and critical at 90% or above. |

Memory categories describe the **current context snapshot** and should not overlap:

| Field | Context content |
| --- | --- |
| `system` | System instructions and persistent prompt rules. |
| `conversation` | Messages and conversation history. |
| `working` | Agent working memory and task state included in context. |
| `retrieved` | Retrieved documents, facts, or memory snippets. |
| `tools` | Tool outputs included in context. |

```text
used = system + conversation + working + retrieved + tools
utilization (%) = used / capacity × 100
cost (USD) = (input_tokens × input_rate + output_tokens × output_rate) / 1,000,000
```

Context snapshots and billable tokens serve different purposes. Report `input_tokens` and `output_tokens` for **each model call**, rather than cumulative session counters. Report current memory category totals for the snapshot. Context is allowed to exceed capacity so overflow remains visible.

Prices are supplied by the integrator in USD per million tokens. Estimates do not automatically account for cached-token pricing, billing tiers, discounts, or other provider charges. Missing rates default to zero.

## Connect an agent

After a model call, send one event with the session identifiers, current context categories, and that call’s billable token counts. Use counts from your agent’s instrumentation and provider usage response where available.

```sh
curl http://127.0.0.1:8000/api/events \
  -H 'Content-Type: application/json' \
  -d '{
    "workspace": 1,
    "session": "run-001",
    "agent": "Research agent",
    "model": "my-model",
    "capacity": 128000,
    "system": 2400,
    "conversation": 16000,
    "working": 8000,
    "retrieved": 4000,
    "tools": 1200,
    "input_tokens": 31600,
    "output_tokens": 800,
    "input_rate": 2.50,
    "output_rate": 10.00
  }'
```

A successful submission returns HTTP `201` with the stored event ID:

```json
{"id": 1}
```

The example contains illustrative prices. Replace them with the rates applicable to your model. The dashboard’s **Copy API example** button includes the currently selected workspace ID and application port.

### Event validation

| Fields | Rules |
| --- | --- |
| `workspace` | Existing positive integer workspace ID; defaults to `1`. |
| `session`, `agent`, `model` | Required non-empty strings, each at most 160 characters. |
| `capacity` | Required integer from 1 through 1,000,000,000. |
| Memory categories, `input_tokens`, `output_tokens` | Integers from 0 through 1,000,000,000; omitted fields default to zero. |
| `input_rate`, `output_rate` | Finite numbers from 0 through 1,000,000; omitted fields default to zero. |

The server assigns a UTC ingestion timestamp. Client-supplied timestamps are not used. POST bodies must be JSON objects no larger than 64 KB.

Events are append-only and submissions are not deduplicated. Sending the same model call twice will count its cost twice.

## HTTP API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/workspaces` | List workspace IDs and names. |
| `POST` | `/api/workspaces` | Create a workspace from `{"name":"Research"}`. |
| `GET` | `/api/events?workspace=1` | Read all events in one workspace, including computed `used` and `cost` fields. |
| `POST` | `/api/events` | Store an event using the payload described above. |
| `POST` | `/api/demo` | Load sample events using `{"workspace":1}`. |

Workspace IDs default to `1` when omitted from event queries, event submissions, or demo requests. A demo request without a workspace should still send a JSON object: `{}`.

Workspace names must contain 1–60 characters after trimming. Duplicate names are rejected case-insensitively with HTTP `409`. Invalid request values return HTTP `400` with an `error` field. Unknown routes return HTTP `404`.

Create a workspace:

```sh
curl http://127.0.0.1:8000/api/workspaces \
  -H 'Content-Type: application/json' \
  -d '{"name":"Research team"}'
```

Use the returned `id` for that workspace’s submissions and queries:

```sh
curl 'http://127.0.0.1:8000/api/events?workspace=2'
```

## Architecture and files

```text
Agent instrumentation
        │ POST /api/events
        ▼
Python HTTP server ─── SQLite (memory.db)
        ▲
        │ GET /api/events?workspace=...
        │ every five seconds
Browser dashboard
```

```text
main.py                    HTTP server, validation, SQLite storage, demo generation
static/
  index.html               Dashboard, workspace controls, and integration example
  style.css                Responsive layout and background themes
  app.js                   API requests, charts, filtering, and export
  netrootai-logo.png        Netroot AI branding
test_main.py               API, validation, migration, and workspace tests
memory.db                  Runtime database, created automatically and gitignored
README.md                  Setup and usage documentation
```

## Storage and local access

The server binds to `127.0.0.1`. Events and workspace names are saved in `memory.db` beside `main.py`. Existing events from earlier versions are assigned to **My workspace** (ID `1`) automatically at startup.

The application stores token counts, identifiers, rates, and timestamps rather than prompt or tool-result text. Browser local storage remembers only the selected workspace and theme.

Workspaces organize local data; they do not provide user accounts, authentication, or access control. Anyone who can access the local service can view and switch workspaces. Keep this development service local.

There is no retention policy, deletion UI, pagination, or background aggregation. Each refresh loads all events in the selected workspace into the browser, so this implementation is best suited to local development and smaller datasets. It does not manage agent memory, perform retrieval, or compact context automatically.

## Tests

Run the standard-library test suite:

```sh
python -m unittest -v
```

Tests use temporary databases and localhost HTTP servers. They cover ingestion, cost calculations, persistence, invalid values, workspace separation, workspace-name validation, existing-data migration, demo loading, and static dashboard routes.

## Troubleshooting

| Issue | What to check |
| --- | --- |
| Overview is empty | Select the correct workspace, choose All data, clear agent filters, or load demo data. |
| Submitted events are missing | Check the workspace ID in your payload and confirm the API returned HTTP `201`. |
| Estimated spend is zero | Include nonzero billable token counts and the applicable per-million-token rates. |
| Port is already in use | Start with `python main.py --port 8080` and open the matching URL. |
| Backend changes are not visible | Restart `main.py`, then refresh the page. |
| The database cannot be written | Ensure the application directory and `memory.db` are writable. |
