# Expense Tracker — FastAPI / PostgreSQL assessment

Backend assessment implementation. Python 3.11+, FastAPI, Pydantic v2, async SQLAlchemy 2.x, Alembic, PostgreSQL, Redis, aioboto3 and asynchronous CSV uploads. All API routes (including health) are under **`/api/v1`**.

> **Assessment status :** The source ZIP includes **86 test functions** (plus parametrized cases), including all Part 3 mandatory scenarios and mocked S3 security cases. **36 dependency-independent tests passed in the authoring environment**. The full PostgreSQL/Redis/S3-mock integration suite has **not been executed here**, because live PostgreSQL/Redis and several optional Python dependencies were unavailable. **Measured full-suite coverage: not yet available.** **Required coverage: ≥85%.** Do not submit a claim of 85% until `pytest` completes and the measured TOTAL meets the threshold. Fill in the actual percentage after running locally/CI: `TOTAL = ______%`.

## Code architecture

The implementation keeps the existing **domain / use-case / infrastructure / API / composition-root** structure from the supplied source. It is an application-centric variant of Clean Architecture, not a claim of framework-independent SQLAlchemy entities. CA provide much cleaner code management and structuring. 

```text
src/
├── domain/
│   ├── models/                  # SQLAlchemy mapped entities, shared Base and relationships
│   ├── policies/                # Pure budget threshold rules
│   ├── value_object/            # Money (Decimal invariant)
│   └── exceptions.py            # Domain level exception or error
├── usecase/
│   ├── context/                 # CurrentUser: authenticated request identity
│   ├── dto/                     # Pydantic use-case request/result DTOs
│   ├── interactors/             # Application use cases / handlers
│   ├── interfaces/              # Protocol ports for external dependencies
│   └── validator.py             # business validation class
├── infrastructure/
│   ├── adapters/                # PostgreSQL, Redis authentication, S3, reporting, CSV
│   ├── database/                # Async engine, session factory, transactional lifecycle
│   └── worker.py                # Outbox, receipt cleanup and import worker
├── api/
│   ├── v1/                     # HTTP routers (thin controllers)
│   └── exception_handlers.py   # Consistent error response that will be return from API endpoints in case of errors
└── main/
    ├── ioc/                    # DI: ports -> adapters, request-scoped session
    ├── config.py               # Environment-based settings
    ├── api_version.py          # /api/v1
    └── app.py                  # FastAPI composition root
alembic/                         # Versioned migrations (PostgreSQL)
tests/unit/                     # Domain and contract tests, no database
tests/integration/              # Real PostgreSQL, Redis, httpx.AsyncClient
compose.test.yaml                # Disposable local test infrastructure
requirements.txt                # Runtime dependencies
requirements/dev.txt            # Test dependencies
postman/expenses.postman_collection.json
```

**Dependency direction:** API controllers call application interactors; interactors depend on application interfaces (ports). Infrastructure adapters implement those interfaces; the `main/ioc` composition root selects concrete adapters. The Pydantic DTOs are returned to HTTP handlers rather than ORM entities. Money uses `Decimal` and SQL `NUMERIC`, not Python floats. 

The supplied implementation uses SQLAlchemy mapped classes in `src/domain/models/`. This is done for the 48-hour scope but means that part of the domain depends on SQLAlchemy. 

**Read/write paths:** ORM and SQLAlchemy expressions handle most CRUD, idempotency and optimistic locking; optimized PostgreSQL SQL is used for currency reporting and aggregated categories.

## Setup — Python, PostgreSQL and Redis

1. Use Python **3.11 or newer** and create a virtual environment:
   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements/dev.txt
   ```
   Use `python3.11 -m venv .venv` on Linux/macOS. The supplied package version ranges are retained in `requirements.txt`.
2. Copy `.env.example` to `.env` and set your **own** database URL, Redis URL and a freshly generated `JWT_SECRET` (`python -c "import secrets; print(secrets.token_urlsafe(48))"`). Never commit `.env`, passwords or credentials. Test infrastructure below has **test-only** credentials.
3. Create the PostgreSQL database, then apply **existing Alembic migration** from the repository root:
   ```powershell
   python -m alembic upgrade head
   ```
   `alembic/env.py` reads `DATABASE_URL` from the environment or `.env`. Its `target_metadata` imports all SQLAlchemy models.
4. Seed at least 90 days of PKR, AED, USD and EUR rates:
   ```powershell
   python -m scripts.seed_rates
   ```
5. Run the API and separately run the background worker:
   ```powershell
   python -m uvicorn src.main.app:app --reload
   # In a different terminal (same environment):
   python -m src.infrastructure.worker
   ```
6. Open `http://localhost:8000/docs`. Endpoints use `/api/v1/auth`, `/api/v1/categories`, `/api/v1/expenses`, `/api/v1/reports/monthly`, `/api/v1/imports/{job_id}`, `/api/v1/notifications` and `/api/v1/expenses/{id}/receipt/...`.

**S3/MinIO:** The adapter expects a private bucket (`STORAGE_BUCKET`). Production uses the IAM task role (no static access key). For local MinIO, configure the internal endpoint **and a client-reachable presigned URL endpoint**; a URL pointing to a Docker-only hostname will not work from a browser. The S3 client is mocked in tests; **no real AWS call** occurs in any test.

## Run every test with exactly one command: `pytest`

The assessment requires real PostgreSQL; **SQLite is not a substitute**. Test infrastructure is independent of your application database.

1. Install `requirements/dev.txt` (includes `pytest`, `pytest-asyncio`, `httpx`, `pytest-cov`, and optional `moto[s3]`). VS Code must use the same `.venv` interpreter.
2. Start disposable PostgreSQL + Redis (Docker required):
   ```powershell
   docker compose -f compose.test.yaml up -d --wait
   ```
3. In the **same PowerShell session**, explicitly target the test services:
   ```powershell
   $env:DATABASE_URL="postgresql+asyncpg://expense:test-only-password@localhost:5435/expenses_test"
   $env:REDIS_URL="redis://localhost:6380/1"
   $env:JWT_SECRET=(python -c "import secrets; print(secrets.token_urlsafe(48))")
   $env:IMPORT_SPOOL_DIR=".data/imports-test"
   python -m alembic upgrade head
   pytest
   ```
   On Linux/macOS, use `export` rather than `$env:`. Test fixture refuses to truncate unless the PostgreSQL database is **exactly** `expenses_test`, and refuses Redis `FLUSHDB` unless the URL ends with `/1`. The fixture truncates all mapped tables and seeds exchange rates before **every** integration test. Never use real customer data in this database.
4. `pytest.ini` configures `pytest-asyncio` (`asyncio_mode=auto`), marker registration, and an automatic `pytest-cov` coverage gate: **`--cov=src --cov-report=term-missing:skip-covered --cov-report=xml:coverage.xml --cov-fail-under=85`**. The command exits nonzero if any test fails or coverage is below 85%.
5. For fast *unit-only* debugging without the global coverage threshold, run:
   ```powershell
   python -m pytest tests/unit -v -o addopts="--strict-markers"
   ```
   Unit-only coverage is not representative of whole-project coverage. The **actual complete coverage percentage** must be copied from the successful `pytest` output into this README before submission. Generate an optional HTML report with `pytest --cov-report=html` after the services are running.

### Required Part 3 test coverage matrix

| PDF requirement | Tests / file | Approach |
|---|---|---|
| Refresh token reused twice revokes all sessions | `tests/integration/auth/test_auth.py::test_refresh_replay_revokes_all` | PostgreSQL + httpx, verifies old and rotated access tokens |
| Sixth failed login 429 and Retry-After | `test_sixth_failure_rate_limited` | Real Redis Lua policy |
| Other user's expense 404 | `tests/integration/expenses/test_expenses.py::test_other_users_expense_returns_404` | Ownership boundary via API |
| Zero / negative / 3 decimals rejected | `test_expense_invalid_amount` + unit DTO tests | Parametrized request and domain validation |
| Cursor stable after inserted rows | `test_cursor_no_duplicates_after_insert` | Real PostgreSQL keyset pagination |
| Multi-currency reporting + fallback rate | `tests/integration/reports/test_reports.py::test_monthly_report_mixed_currency_with_rate_fallback` | Real PostgreSQL SQL reporting |
| Simultaneous Idempotency-Key posts | `test_parallel_post_idempotency` | `asyncio.gather`, one expense row |
| Simultaneous PATCH same ETag | `test_parallel_patch_one_wins` | `asyncio.gather`, one 200 / one 412 |
| Outbox event reprocessed twice | `tests/integration/notifications/test_notifications.py::test_budget_alert_once_even_if_reprocessed` | Unique constraint and repeated worker delivery |
| CSV good + invalid rows with counts | `tests/integration/imports/test_imports.py::test_csv_import_mixed_rows` | Worker + persisted import errors |
| Private receipt upload and forged extension | `tests/unit/test_receipt_storage.py`, `tests/integration/receipts/test_receipts.py` | Entirely mocked S3; fake `MZ` executable named `.png` |

Additional tests cover login, logout, invalid JWTs, filter/cursor tampering, `If-Match` requirements, category uniqueness, report deltas, duplicate import, foreign user's jobs, receipt ownership, cleanup scheduling, domain invariants, and missing/excessive receipt sizes. The existing unit and integration tests are preserved rather than replaced.

### Current validation vs outstanding evidence

- **Passed here:** 36 self-contained unit tests; Python compilation; model-independent validation.
- **Not run here:** PostgreSQL/Redis integration suite and mocked S3 adapter tests (required packages/services unavailable in this sandbox).
- **Not asserted:** The 85% full-suite coverage threshold; it must be **measured** with the `pytest` command above and recorded as an actual percentage.
- **Review preparation:** Read `tests/integration/conftest.py` (destructive fixture safety), `src/infrastructure/adapters/expenses.py` (atomic concurrency), `src/infrastructure/adapters/reports.py` (SQL query), `src/infrastructure/worker.py` (outbox), and `src/infrastructure/adapters/s3.py` (receipt validation).

## Implementation notes relevant to the assessment

- Access JWTs last 15 minutes. Refresh tokens last 7 days, are stored as hashes, and rotate. Reuse increments the user's `session_version` and revokes refresh sessions.
- Redis Lua scripts manage per-email failed login counts and in-flight attempts for consistent throttling across multiple API servers. Login fails closed with 503 when Redis is unavailable.
- Idempotency is anchored by a PostgreSQL unique constraint `(user_id, key)` and stored response payload with 24-hour expiry. Redis is **not** the source of truth for expense idempotency.
- Expense ETags encode the integer version. `UPDATE ... WHERE version=:expected` ensures atomic optimistic concurrency. Missing If-Match returns 428; stale ETag returns 412.
- Listing uses `(spent_on DESC, id DESC)` keyset pagination with an initial `created_at` cut-off and signed filter-bound cursor to reduce duplicates/omissions when new expenses arrive.
- Exchange-rate fallback finds the latest rate at or before `spent_on` and reports in user's base currency. Monetary conversions use SQL `NUMERIC`/Python `Decimal`.
- Expense and budget outbox events commit in the same PostgreSQL transaction. `notifications` has unique `(category_id, month, level)` and worker uses `ON CONFLICT DO NOTHING` so repeated deliveries do not duplicate alerts. Current rule emits alerts on upward threshold crossings; lowering spend does not retract past notifications, and later re-crossings cannot create duplicates for the same category/month/level.
- CSV imports accept up to 100,000 rows, use chunked file spooling and batch insertion, and have a durable PostgreSQL import job. Same-user duplicate uploads use the content SHA-256. Production needs a **shared durable spool**, not local disk when running multiple API/worker instances (see short answer 3).
- Private S3 presigned POST limits size and content type. Confirmation checks object existence, size, and magic bytes, then persists the object key. Receipt deletion creates retryable cleanup work; tests use mocks instead of AWS.

## Part 4 — AWS deployment notes

### API / worker; scaling and zero downtime

- **ECS Fargate** is a suitable deployment target: start with two API tasks in distinct Availability Zones behind an Application Load Balancer (ALB), autoscale based on request latency/CPU and load.
- Run the background worker as an **independent ECS service**, initially one task. Increase workers after measuring PostgreSQL load; the outbox uses `FOR UPDATE SKIP LOCKED` to avoid double claims, and unique notification constraints handle retries.
- Set task health checks on `/api/v1/health` plus real readiness checks. Configure ALB target deregistration delay and ECS rolling deployment with minimum healthy capacity.
- Publish immutable tagged container images to ECR. Roll forward/back application tasks while maintaining compatible database schemas; do not rebuild the image independently across environments.
- The worker should drain or relinquish leases on shutdown; ECS restarts unhealthy tasks. Track outbox backlog, retry count, import age, API p95, and DB connections.

### RDS PostgreSQL and secrets

- Deploy RDS PostgreSQL Multi-AZ in **private subnets**, without public access; take automated backups and verify point-in-time recovery.
- RDS security group: **inbound TCP 5432 only from the API/worker ECS task security group** (and tightly controlled migration task security group), not from `0.0.0.0/0`.
- ECS tasks use separate security groups. Outbound connection to RDS on 5432, Redis on 6379 TLS, and S3 endpoints only as needed.
- Supply credentials via **AWS Secrets Manager** or encrypted SSM parameters injected at runtime; never store passwords or signing keys in repository, task definitions, container image or logs.
- Size the SQLAlchemy async connection pool to avoid connection exhaustion when API tasks scale, and monitor locks, slow queries, CPU and RDS IOPS. Use TLS for PostgreSQL connections.

### ElastiCache Redis and failure policy

- Use ElastiCache Redis/Valkey in private subnets with authentication/TLS and access only from ECS task security groups on TCP 6379; do not expose it publicly.
- Redis supports the 5-failures/15-minute login limit using atomic Lua scripts. In the current code, Redis failures cause authentication to **fail closed with 503** rather than allow unlimited login attempts.
- Database-backed `IdempotencyRecord` is the durable authority for expense retry safety; losing Redis does **not** cause duplicate expenses.
- The worker uses Redis only as a wake-up hint: if Redis is down, it keeps polling PostgreSQL. Queueing, leases and outbox records remain durable in PostgreSQL.
- For multi-AZ, enable appropriate ElastiCache failover and monitor throttling/availability metrics; handle outages without masking them as successful authentication.

### S3 private bucket and least-privilege IAM

- Disable public access, enforce bucket-owner ownership, enable encryption and SSL-only access; use a private bucket and per-user prefix `receipts/{user_id}/{expense_id}/{uuid}.{ext}`.
- ECS uses a **task IAM role** (no embedded access keys). The API generates upload/download presigned links; it doesn't transfer receipt bytes through the API. The worker performs deletion and cleanup. Restrict bucket policies so other principals cannot access the objects.
- Example **API task role** policy (replace bucket name; object resource only; no `ListBucket` needed):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "SignedReceiptUploadsAndDownloads",
    "Effect": "Allow",
    "Action": ["s3:PutObject", "s3:GetObject"],
    "Resource": "arn:aws:s3:::REPLACE_PRIVATE_BUCKET/receipts/*"
  }]
}
```

- Example **worker task role** policy (only deletion; if worker needs other S3 actions, document and grant them explicitly):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "DeleteOrphanAndExpiredReceipts",
    "Effect": "Allow",
    "Action": "s3:DeleteObject",
    "Resource": "arn:aws:s3:::REPLACE_PRIVATE_BUCKET/receipts/*"
  }]
}
```

- `HeadObject` is authorized by `s3:GetObject`. IAM task-role permissions are not equivalent to application authorization: the API must separately validate expense ownership and issuance of a receipt upload intent before signing any URL.
- If using SSE-KMS, add only the KMS actions that the selected operations require and restrict to the specific key. Use bucket lifecycle cleanup policies and audit events as defense in depth.

### Safe Alembic migrations during deployments

1. Before rollout, run migration dry-runs/test against a restored staging DB and back up the current RDS state.
2. Apply **expand** migrations first via a **single deployment job/ECS task**, with DB permissions narrowly scoped for schema changes; never run competing migrations on every API replica.
3. Prefer additive nullable columns/new tables/new indexes (use `CREATE INDEX CONCURRENTLY` for large production tables, outside regular transactions where required). Avoid instantly dropping or renaming columns used by old tasks.
4. Deploy new app tasks while old tasks remain healthy; backfill large tables asynchronously in controlled batches. Observe application health and errors.
5. Only in a later release, after all old tasks are gone, execute **contract** migrations that remove old columns or tighten constraints. Roll back the app image separately from schema changes when possible.

## Part 4 — Five short written answers (5–10 lines each)

### 1. Why pre-signed S3 upload URLs instead of sending the file through the API? What can go wrong?

1. Presigned POST lets the client send file bytes to S3 directly, avoiding API memory, bandwidth, and request-time overhead.
2. The API authenticates ownership and issues a short-lived, uniquely scoped key for that specific expense.
3. Include a 5 MB content-length condition, allowed declared MIME types and a 15-minute signing expiry.
4. A presigned link is a bearer capability: someone who obtains it may upload until expiry; enforce TLS, short TTL and unpredictable object keys.
5. Filename and `Content-Type` are not trustworthy; confirm upload using `HeadObject` and inspect file signature bytes through a ranged GET.
6. Verify uploaded key matches a stored, non-expired intent for the current user and expense; reject missing, oversized or mismatched files.
7. A valid signature is not antivirus protection: scan suspicious content asynchronously if needed, keep bucket private and delete abandoned uploads.

### 2. GET /expenses slows down at 20 million rows. How would you investigate and fix it?

1. Measure p50/p95/p99 latency and capture representative SQL, row counts, parameters and query frequency (e.g., `pg_stat_statements`).
2. Run `EXPLAIN (ANALYZE, BUFFERS)` on slow queries to inspect sequential scans, sorts, heap reads, row misestimates and I/O.
3. The standard owner-keyset query needs a composite index aligned to `WHERE user_id = ? ORDER BY spent_on DESC, id DESC`, e.g. `(user_id, spent_on DESC, id DESC)`.
4. Maintain appropriate additional indexes only for frequently used selective predicates, such as category/date; indexes increase write cost.
5. Avoid deep `OFFSET` pagination: the database must scan/discard skipped rows. Use `(spent_on, id) < (:date, :id)` keyset pagination.
6. Return only requested columns, use `LIMIT`, and avoid loading SQLAlchemy entity relationships that the response doesn't need.
7. Inspect N+1 patterns with SQL logging/profiling; use eager loading or joins to fetch category details in predictable round trips.
8. Recheck with production-like data, index statistics, and the same concurrency to verify improved plans and reduced buffer usage before considering partitioning.

### 3. API on three servers behind a load balancer: what breaks and how do you make it safe?

1. Access JWTs are stateless, but revocation is checked against `session_version` in PostgreSQL, so each server sees the same user state.
2. Refresh tokens are hashed and rotated in PostgreSQL, using row locks; replays revoke sessions across all API servers.
3. Rate-limiting counters and pending login attempts must be shared in Redis; local per-process dictionaries would allow bypass.
4. Expense idempotency must be database-backed with a unique key and atomic transaction; the Redis notification hint is not a durable lock.
5. The outbox worker can run on separate hosts via PostgreSQL leases and `SKIP LOCKED`; notification uniqueness handles redelivery.
6. S3 receipts are shared, but **the present CSV spool is local disk**, so multi-instance deployment requires moving the import spool to private S3/EFS and storing its URI in import jobs.
7. Run Alembic once in the deployment pipeline, not at startup on all three API hosts; deploy backward-compatible schema changes first.
8. The ALB should use readiness checks, controlled task draining, common logging/correlation IDs and correctly scoped secrets/network policies.

### 4. Outbox worker down 2 hours; 500,000 events backlog: what happens on recovery?

1. PostgreSQL retains outbox rows, so queued events are not lost; the user-facing API can continue committing transactions while the worker is unavailable.
2. The worker currently selects up to **100** ready events per batch with `FOR UPDATE SKIP LOCKED`; additional worker instances can claim disjoint rows.
3. Do not start thousands of workers immediately; scale concurrency in steps while observing DB CPU, connections, locks, replication lag and application p95.
4. Use bounded batches/transactions and a separately sized DB pool so backlog processing does not starve online requests.
5. Retry transient failures with exponential backoff; quarantine poison events and alert when retry counts or oldest-event age cross thresholds.
6. Unique `(category_id, month, level)` notification constraints make repeated outbox deliveries idempotent, including crash/replay windows.
7. Publish metrics for backlog count, event age, throughput and failure rate; estimate catch-up time from measured rows/second and adjust worker capacity cautiously.
8. If bursts persist, partition/archive processed records and optimize the ready-event index; do not full-scan or load 500,000 rows into Python memory.

### 5. Describe a conscious simple-over-perfect trade-off from this code.

1. The implementation uses PostgreSQL as its durable outbox/job coordination mechanism, with optional Redis wake-up signals.
2. This avoids deploying Kafka/RabbitMQ just to send budget notifications and claim CSV import work in a limited assessment.
3. A single database transaction gives clear atomic semantics between the expense write and outbox event creation.
4. Worker concurrency is controlled with `SKIP LOCKED` and business-level unique constraints rather than complex distributed coordination.
5. The trade-off is additional PostgreSQL polling and contention as event volume grows, particularly during backlog recovery.
6. A future design could relay events to a broker while still retaining the transactional outbox, idempotent consumers and retry semantics.
7. I prioritized a small, explainable, testable solution with explicit failure modes over premature event-bus complexity.

## Final submission checklist

- [x] Existing FastAPI API under `/api/v1`, DTOs, migrations, Redis, transactional outbox, streaming CSV, and private receipt support retained.
- [x] More than 30 pytest test functions, including all required hard-feature scenarios and mocked S3 tests.
- [x] `pytest` configured as a one-command test run with a minimum 85% coverage gate.
- [x] Disposable PostgreSQL/Redis test Compose, migration instructions and safety checks included.
- [x] AWS API, worker, RDS, ElastiCache, S3 least-privilege IAM and migration notes documented.
- [x] Five written architectural answers included above.
- [x] Original 19-route Postman collection retained; it should be verified against your running OpenAPI document.
- [x] **Run full PostgreSQL/Redis test suite locally/CI and fix any failures.**
- [ ] **Record actual coverage percentage at the top of this README; must be ≥85%.**
- [ ] Validate production-like container build and test S3/MinIO configuration outside unit tests.
- [ ] Move CSV file spool to shared S3/EFS before horizontally scaling API and worker services.
- [ ] Do a final secret scan before GitHub submission; add reviewers as collaborators if repository is private.

**AI disclosure (assessment requirement):** AI-assisted tooling was used to help S3 mocks, coverage configuration and AWS deployment notes

---

## Appendix — Running integration tests and coverage locally from VS Code

These instructions use your **existing local PostgreSQL server** and the Redis 8 Docker container already published on `localhost:6379`. There is **no need to deploy the FastAPI application** or start Uvicorn to run the `httpx.AsyncClient` integration suite.

### 1. Create a dedicated PostgreSQL test database

You can use the **same PostgreSQL server** as your application, but you must create a **separate database**. Open pgAdmin Query Tool while connected to an existing database (such as `postgres`) and run:

```sql
CREATE DATABASE expenses_test;
```

> **Safety:** Do not run the integration tests against your normal application database. The `clean_db` fixture truncates tables before tests. Your existing fixture requires the database name to be exactly `expenses_test`.

From the VS Code PowerShell terminal, go to the project root and set a connection URL with **your real local PostgreSQL credentials and port**:

```powershell
cd C:\expense_tracker
$env:DATABASE_URL="postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/expenses_test"
```

Replace `YOUR_PASSWORD` and `5432` if your installation uses a different password or port. A password containing URL-reserved characters such as `@`, `#`, or `/` must be percent-encoded in the connection URL.

### 2. Apply Alembic migrations to the test database

Your `alembic/env.py` reads its connection configuration from the environment or `.env`. **Verify that the effective URL points to `expenses_test`** before applying migrations; the environment variable must take precedence for this terminal session.

```powershell
python -m alembic upgrade head
```

Do not run migrations against your normal development database while setting up the test database.

### 3. Reuse your running Redis container

Your existing Redis Docker container exposes host port **6379**, not 6380. Configure integration tests to use database **1**:

```powershell
$env:REDIS_URL="redis://localhost:6379/1"
```

Check it from PowerShell:

```powershell
docker exec redis redis-cli -n 1 PING
```

Expected result: `PONG`. Database 1 is logically separate from database 0, but confirm that **no other application uses Redis DB 1**, because the test fixtures may clear its keys. Run pytest from the same PowerShell session so the environment variables are inherited.

### 4. Run tests from VS Code

First execute only integration tests without the global coverage gate, to troubleshoot failures:

```powershell
python -m pytest tests/integration -x -v -o "addopts="
```

Run unit tests independently:

```powershell
python -m pytest tests/unit -v -o "addopts="
```

Once PostgreSQL and Redis are reachable and integration tests pass, execute the full suite with the project's configured coverage requirement:

```powershell
python -m pytest
```

### 5. Generate pytest coverage reports

Install the coverage plugin if it is missing:

```powershell
python -m pip install pytest-cov
```

From the project root, generate terminal, HTML, and XML coverage reports while enforcing the **85% minimum**:

```powershell
cd C:\expense_tracker
python -m pytest --cov=src --cov-report=term-missing --cov-report=html --cov-report=xml:coverage.xml --cov-fail-under=85
```

Your `pytest.ini` already defines coverage options under `addopts`. The command above can repeat report settings; that is harmless for most configurations, but to **replace** all configured coverage flags with precisely these reports, use:

```powershell
python -m pytest -o "addopts=" --cov=src --cov-report=term-missing --cov-report=html --cov-report=xml:coverage.xml --cov-fail-under=85
```

| Report | Location | Purpose |
|---|---|---|
| Terminal coverage summary | VS Code terminal | Overall percentage and uncovered lines |
| HTML | `htmlcov/index.html` | Browse coverage by file and line |
| XML | `coverage.xml` | CI/CD or assessment tooling |

Open the HTML report from PowerShell:

```powershell
start .\htmlcov\index.html
```

**Illustrative output only — not measured project coverage:**

```text
Name                              Stmts   Miss  Cover
-----------------------------------------------------
src/usecase/expenses.py             120     10    92%
src/usecase/auth.py                 100     15    85%
src/infrastructure/database.py       80      8    90%
-----------------------------------------------------
TOTAL                               300     33    89%
```

### 6. Check the 85% assessment requirement

The assessment requires **85% or higher coverage** across the **complete unit and integration suite**. Since `pytest.ini` already contains `--cov-fail-under=85`, the simplest final command is:

```powershell
python -m pytest
```

To inspect the current percentage **without failing merely because coverage is below 85%**, temporarily override the configuration:

```powershell
python -m pytest -o "addopts=" --cov=src --cov-report=html --cov-report=term-missing --cov-fail-under=0
```

A passing test suite does **not** automatically mean 85% coverage. After running all tests successfully, copy the actual `TOTAL` value from pytest into the assessment-status section at the top of this README. Do not substitute the example percentages above for the measured result.
