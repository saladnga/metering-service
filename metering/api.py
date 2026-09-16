from fastapi import FastAPI
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field
from metering.db import pool
from metering.ingest import insert_events
from datetime import datetime
from typing import Literal

app = FastAPI()


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    return {"status": "ready"}


class EventIn(BaseModel):
    event_id: UUID
    tenant: str
    metric: str
    quantity: Decimal = Field(gt=0)
    event_time: datetime


@app.post("/v1/events")
def create_events(events: list[EventIn]):
    event_dict = [
        {
            "event_id": e.event_id,
            "tenant": e.tenant,
            "metric": e.metric,
            "quantity": e.quantity,
            "event_time": e.event_time,
        }
        for e in events
    ]
    accepted, duplicates = insert_events(event_dict)
    return {"accepted": accepted, "duplicates": duplicates}


@app.get("/v1/usage")
def get_usage(
    tenant: str,
    metric: str,
    start: datetime,
    end: datetime,
    granularity: Literal["hour", "day"] = "hour",
    as_of: datetime | None = None,
):
    table = "hourly_rollups" if granularity == "hour" else "daily_rollups"

    query = f"""
        SELECT COALESCE(SUM(quantity), 0)
        FROM (
            SELECT DISTINCT ON (bucket_start) quantity
            FROM {table}
            WHERE tenant = %s AND metric = %s AND bucket_start >= %s AND bucket_start < %s {"AND computed_at <= %s" if as_of else ""}
            ORDER BY bucket_start, computed_at DESC
        ) latest_per_bucket
    """

    params = [tenant, metric, start, end]
    if as_of:
        params.append(as_of)

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            total = cur.fetchone()[0]
    return {"tenant": tenant, "metric": metric, "total": total}
