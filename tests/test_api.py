import datetime
import uuid

from fastapi.testclient import TestClient

from metering.api import app
from metering.rollup import recompute_hour

client = TestClient(app)


def test_health_and_ready():
    r1 = client.get("/healthz")
    assert r1.status_code == 200
    assert r1.json() == {"status": "ok"}

    r2 = client.get("/readyz")
    assert r2.status_code == 200
    assert r2.json() == {"status": "ready"}


def test_post_events_dedupes():
    tenant = f"test-{uuid.uuid4()}"
    batch = [
        {
            "event_id": str(uuid.uuid4()),
            "tenant": tenant,
            "metric": "token_output",
            "quantity": 100,
            "event_time": "2026-01-01T00:00:00Z",
        },
        {
            "event_id": str(uuid.uuid4()),
            "tenant": tenant,
            "metric": "token_output",
            "quantity": 200,
            "event_time": "2026-01-02T00:00:00Z",
        },
        {
            "event_id": str(uuid.uuid4()),
            "tenant": tenant,
            "metric": "token_output",
            "quantity": 30,
            "event_time": "2026-01-03T00:00:00Z",
        },
    ]
    response1 = client.post("/v1/events", json=batch)
    assert response1.status_code == 200
    assert response1.json() == {"accepted": 3, "duplicates": 0}

    response2 = client.post("/v1/events", json=batch)
    assert response2.status_code == 200
    assert response2.json() == {"accepted": 0, "duplicates": 3}


def test_post_events_rejects_negative_quantity():
    tenant = f"test-{uuid.uuid4()}"
    batch = [
        {
            "event_id": str(uuid.uuid4()),
            "tenant": tenant,
            "metric": "token_output",
            "quantity": -15,
            "event_time": "2026-01-04T00:00:00Z",
        },
    ]
    response = client.post("/v1/events", json=batch)
    assert response.status_code == 422


def test_usage_endpoint_reflects_rollup():
    tenant = f"test-{uuid.uuid4()}"
    metric = "token_output"
    hour_start_str = "2026-01-01T15:00:00Z"
    hour_start = datetime.datetime(2026, 1, 1, 15, 0, 0, tzinfo=datetime.timezone.utc)

    batch = [
        {
            "event_id": str(uuid.uuid4()),
            "tenant": tenant,
            "metric": metric,
            "quantity": 200,
            "event_time": "2026-01-01T15:00:00Z",
        },
        {
            "event_id": str(uuid.uuid4()),
            "tenant": tenant,
            "metric": metric,
            "quantity": 100,
            "event_time": "2026-01-01T15:30:00Z",
        },
    ]
    client.post("/v1/events", json=batch)
    recompute_hour(tenant, metric, hour_start)
    response = client.get(
        "/v1/usage",
        params={
            "tenant": tenant,
            "metric": metric,
            "start": hour_start_str,
            "end": "2026-01-01T16:00:00Z",
        },
    )
    assert response.json()["total"] == 300
