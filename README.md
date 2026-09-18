# Metering Service

A usage-metering service - the thing that sits behind a billing system and answers "how much did this customer use?" Clients send events (`tenant`, `metric`, `quantity`, `when`), the service stores them, rolls them into hourly and daily totals, and serves those totals over an API.

Stripe Billing, Orb, Lago, and OpenMeter are all companies that exist to do exactly this. Every AI API company (OpenAI, Anthropic) meters tokens the same way; every cloud provider meters GB-hours and requests the same way. This is a small version of that product category.

## What This Project Demonstrates

> - Events arrive duplicated, out of order, and hours late. An event that happened at 3:00pm can land at 4:15pm — after the 3pm total was already computed and possibly already billed.
> - **The service counts correctly anyway: never double, never dropped, and every historical number stays exactly reproducible, no matter how many times you recompute it.**

## Quickstart

```
git clone <this repo>
cd metering-service
make demo
```

The command: builds the API image, brings up Postgres + the API via Docker Compose, runs migrations, generates 10,000 realistic messy events (duplicates, late arrivals, shuffled order), ingests them, rolls them up, delivers a late batch, recomputes, and prints the totals changing correctly in front of you. No AWS account and no cloud credentials involved beyond Docker.

## Late Data Is A Problem

A mobile SDK buffers events offline and flushes hours later. A region has a network partition and replays its queue on reconnect. A batch job reports yesterday's usage this morning. Every one of these produces an event whose bucket has already closed by the time it arrives — and the two obvious ways to handle it are both wrong:

| Approach | What goes wrong |
|---|---|
| Drop the late event | **Undercharged** — silently giving away paid usage |
| `UPDATE total = total + new` | Works once. A retry (or the job running twice) double-adds it — **overcharged** |
| **Recompute the whole bucket from raw source data** | Correct no matter how many times it runs — this is the idempotent option |

This repo implements the third option, and the design follows directly from it: **every rollup is a pure recomputation from raw events, never an incremental patch.**

## How correctness actually holds together

**Deduplication is enforced by the database, not application code:**

- Every event carries a client-generated `event_id`, the table's primary key.
- Retries use `INSERT ... ON CONFLICT (event_id) DO NOTHING` — a duplicate insert is silently skipped, atomically, inside Postgres.
- A "check then insert" done in application code would have a race between two concurrent requests; a primary key constraint doesn't.

**Rollups are revisions, not overwrites:**

- `hourly_rollups` and `daily_rollups` use a composite primary key of `(tenant, metric, bucket_start, revision)`.
- Recomputing a bucket writes a **new row** — it never destroys the previous answer.
- This is what makes the audit query possible: `GET /v1/usage?...&as_of=<timestamp>` answers "what did this number say before the late data arrived?", not just "what does it say now."
- A recompute that produces the *same* numbers as the current revision is a no-op — no spurious revision gets created for nothing.
- **`event_time` vs `received_at`** is the column pair the whole system turns on. `event_time` is when something happened (decides which bucket it belongs to). `received_at` is when the server learned about it (used for observability, never for bucketing).
- The gap between them, for late-arriving events, is the entire problem this project solves.

**Reconciliation is a second, independent check:**

- The fast path (`recompute_day`) sums already-computed hourly rollups.
- `reconcile` recomputes the same day a completely different way — straight from raw `events` — and compares.
- Agreement is real evidence the fast path is trustworthy; disagreement surfaces a bug immediately instead of quietly billing someone wrong for weeks. It exits non-zero on drift, so a scheduler can actually act on it.

## Architecture

```
   clients                                                    consumers
      │                                                            ▲
      │ POST /v1/events                                           │ GET /v1/usage
      ▼                                                            │
┌─────────────┐        ┌───────────────────┐        ┌──────────────────────┐
│   INGEST    │───────▶│     AGGREGATE      │───────▶│        SERVE          │
│             │  raw   │                    │ small  │                       │
│ events table│  rows  │ hourly/daily       │ totals │ revision-aware query, │
│ (append-    │        │ rollups, always    │        │ ?as_of= audit lookup  │
│  only, PK   │        │ recomputed from    │        │                       │
│  dedup)     │        │ source, never      │        │                       │
│             │        │ patched            │        │                       │
└─────────────┘        └────────────────────┘        └──────────────────────┘
                               ▲
                               │ triggered by CLI (--hour / --backfill),
                               │ scheduled via cron/systemd with a 2-hour
                               │ grace window before closing a bucket
```

## Stack: FastAPI + Postgres, Alembic migrations, Docker Compose locally, Terraform + EC2 on AWS, GitHub Actions for CI/CD

## API

| Endpoint | What it does |
|---|---|
| `GET /healthz` | Is the process alive? (no dependency check) |
| `GET /readyz` | Can this instance actually serve traffic? (real DB check) |
| `POST /v1/events` | Ingest a batch. Returns `{accepted, duplicates}` |
| `GET /v1/usage` | `tenant`, `metric`, `start`, `end`, `granularity=hour\|day`, optional `as_of` |

## Rollup CLI

```
python -m metering.rollup --hour 2026-03-10T15 --tenant acme --metric tokens_output
python -m metering.rollup --backfill 2026-08-01..2026-08-31 --tenant acme --metric tokens_output
python -m metering.rollup --reconcile 2026-08-15 --tenant acme --metric tokens_output
```

The grace window isn't code — it's a calling convention: a scheduled job always asks for `now - 2 hours`, giving stragglers time to land before a bucket is first computed.

## Benchmarks

Measured against a real deployment — AWS EC2 `t3.micro`, Terraform-provisioned, over the real internet, client running on a separate machine so numbers include real network round-trip time.

| Metric | Result | Notes |
|---|---|---|
| Ingestion throughput | **1,232 events/sec** sustained | 50,925 events (50,000 + 5% built-in duplicates) in batches of 1,000, 41.3s wall-clock |
| Query latency (`GET /v1/usage`) | **p50 154ms / p95 200ms** | 30 requests, real network round-trip included |
| Duplicate rejection | **100%** on a full-batch resend (925/925) | Proves deduplication holds for both individual duplicates and a full client-retry scenario |
| Backfill (24 hourly buckets) | **1.3s** | Scales with bucket count, not raw event volume — each bucket is an indexed range scan |
| Reconciliation drift | **Zero** | Independently resumed raw events matched the stored daily rollup exactly (2,454,377 both ways) |

Hardware note: Since this is a small-scaled project, both the API and Postgres run together on the same single `t3.micro`(2 vCPU burstable, 1GB RAM) — no separate database instance, no caching layer.

## Infrastructure

Deployed on a single `t3.micro` EC2 instance running Docker Compose (API + Postgres together) — deliberately no RDS, no load balancer, no Fargate. Provisioned with Terraform: VPC/security group, EC2 + IAM instance role, S3 (archive bucket with a 90-day lifecycle rule), ECR, and an SSM parameter for the database password.

## Running the tests

```
python3 -m pytest -v
```

**The tests:** idempotent ingestion at 10k-event volume, late-arrival convergence (verified against an independently-computed ground truth, not just internal agreement), stable no-op recompute, and the full API surface via FastAPI's `TestClient` against a real (not mocked) database.
