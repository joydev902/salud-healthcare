# Salud MRA — Coding Opportunity Management Platform

Imports Medicare Advantage risk-adjustment coding evidence, consolidates it into opportunities, shows each coder only their assigned providers, and keeps every disposition in an append-only history.

## Dev commands

One command, with Docker:

```bash
docker compose up --build
```

Compose starts PostgreSQL 17, waits for the healthcheck, runs migrations, seeds the demo accounts, and serves the API and the UI. No `.env` file is required. Postgres is published on host port **5433**.

Without Docker (Python 3.12+, Node.js 20+, PostgreSQL 16+):

```bash
createdb -U postgres salud_mra
createdb -U postgres salud_mra_test
python run.py
```

`python run.py` creates the venv, installs dependencies, migrates, seeds, and serves both processes. Copy `.env.example` to `.env` when the database is not `postgres:postgres` on port 5432. Use `http://127.0.0.1`. On some Windows hosts `localhost` resolves to `::1` and the connection is refused.

| URL | |
|---|---|
| http://127.0.0.1:5173 | UI |
| http://127.0.0.1:8000/docs | OpenAPI |
| http://127.0.0.1:8000/api/v1/healthz | Health |

| Command | What it does |
|---|---|
| `python run.py setup` | Create `backend/.venv`, install backend and frontend dependencies |
| `python run.py dev` | Migrate, seed, run API (:8000) and Vite (:5173) |
| `python run.py lint` | ruff, oxlint, prettier --check, tsc |
| `python run.py format` | ruff --fix, ruff format, prettier --write |
| `python run.py test` | pytest against `salud_mra_test` (`TEST_DATABASE_URL` overrides) |
| `python run.py bench` | Load ~200k synthetic rows into `salud_mra_bench`, write `docs/performance.md` |

`BENCH_ROWS` overrides the synthetic row count.

Demo password for every seeded account: `Password123!` (synthetic data only).

| Email | Role | Providers |
|---|---|---|
| admin@salud.test | Admin | all four |
| coder.one@salud.test | Coder | Garcia, Thompson |
| coder.two@salud.test | Coder | Patel, Nguyen |

Sample file: `sample_data/sample_mra_data.csv` (128 rows). Domain notes: [docs/domain-notes.md](docs/domain-notes.md).

## Coverage

| ID | Shipped |
|---|---|
| C1 | CSV upload, missing-column rejection, duplicate fingerprints, import history (file, uploader, time) |
| C2 | Member queue, provider / payer / initiative / disposition filters, member and opportunity drill-down, keyset pages |
| C3 | Confirmed, Denied, Pending chart, Referred to provider; justification required; actor, time, previous and new values |
| C4 | Email and password, Admin and Coder, user admin, provider assignment, scope checked on every request |
| NF1 | Keyset pagination; 200k timings and plans in [docs/performance.md](docs/performance.md) |
| NF2 | Disposition and history committed in one transaction |
| NF3 | Production section below: TLS, encryption at rest, access logs, BAA |

## Architecture

One FastAPI process, one React SPA, one PostgreSQL database. Separate services would not make the audit trail or the queue easier to reason about for this scope. PostgreSQL is the system of record so an opportunity update and its history row commit together. FastAPI gives typed contracts and OpenAPI. React with TanStack Query keeps the queue filters in the URL.

## Data model

- A member is the person (`member_id`), not a policy. One member can have several payer policies.
- An opportunity is `(member, payer, provider, performance year, ICD-10)`. Another initiative for that key is more evidence, not a second review.
- A source row is immutable. Its fingerprint is unique within a file, so re-uploading that file is a duplicate and a new file can still add evidence.
- Performance year comes from `source_file`. A `PY20xx` token wins; otherwise a single `_YYYYMM` stamp is used. Ambiguous or missing years reject the row. PY2024 and PY2025 are different opportunities.
- HCC disagreement is evaluated per member, year, and ICD-10 across payers. Each opportunity keeps the HCC its own sources agree on, and the group is flagged `hcc_conflict`. No payer is preferred.
- Active work is `OPEN`, `PENDING_CHART`, and `REFERRED_TO_PROVIDER`. `OPEN` is the initial state and is not a coder choice. Only coders record dispositions. Admins see only the providers they are assigned; the seed admin is assigned all four so the demo works. Records outside that set return 404.

## API, paging, and performance

Routes live under `/api/v1`: `/auth`, `/imports`, `/members`, `/opportunities`, `/admin`. The session is an HttpOnly `mra_session` cookie. State-changing cookie requests also send `X-Requested-With`.

The queue walks `external_member_id`. The cursor carries a hash of the active filters; a cursor from a different filter set returns 400. Counts are computed for the page just returned. Initiative matching uses `EXISTS`, so an opportunity with two evidence rows is counted once.

On 200k synthetic source rows, typical pages are 4–9 ms and page 201 is about 4.7 ms. Screenings ∩ Denied fell from about 125 ms to about 19 ms after the `(opportunity_id, initiative)` index. Member `ILIKE` search is about 50 ms. Plans are in [docs/performance.md](docs/performance.md).

## Tests

```bash
python run.py test
```

Expect 43 passed. The suite covers year parsing, the sample import and a duplicate re-upload, a missing-column rejection that writes nothing, queue scope and cursors, 404 for an unassigned provider, a stale-version 409, concurrent disposition writers, the CSRF header, and admin self-lockout. Create `salud_mra_test` once, or set `TEST_DATABASE_URL`.

## What I would change for production

This is a local prototype. Real PHI needs the controls below.

**Network and secrets.** TLS at the load balancer, encrypted volumes, `SESSION_COOKIE_SECURE=true`, a random `JWT_SECRET` of at least 32 bytes, and no seeded demo password. The API and the database stay off the public internet. Staging does not receive a copy of production PHI.

**HIPAA hosting.** A BAA-eligible provider with a signed BAA. Revoke `UPDATE` and `DELETE` from the app role on `disposition_history` and `source_records`. Access logs store request id, actor, path, and status. They omit request bodies, which can contain PHI. Keep a retention and legal-hold policy for the history tables.

**Identity.** A short-lived access token plus a rotating refresh token, or OIDC against the organization's IdP. MFA for admins. Logout revokes the session on the server.

**Ingestion.** The single-process import is about 700–860 rows/s. Nightly payer drops should stream the file, batch reference upserts, and move HCC reconciliation off the request. A SHA-256 of the file lets a byte-identical re-upload skip parsing.

**Queue.** Cursor pages stay in the low milliseconds at 200k rows. The remaining outlier is member search. A `lower(external_member_id)` prefix index would bring the `SYN0012%` case down from about 50 ms.

**Runtime.** Serve a built frontend from the same origin as the API. Structured logs and traces on the queue and ingestion paths. The health probe should check the database, not only process liveness.

EHR access, CMS submission, chart uploads, payer feeds, and dashboards are deferred on purpose. They matter in production and they are outside C1–C4.
