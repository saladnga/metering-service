import uuid
import datetime
from metering.db import pool
from metering.ingest import insert_events
from metering.generate import generate_events
from metering.rollup import recompute_hour


def get_total_quantity(tenant):
    sum_quantity = """
        SELECT COALESCE(SUM(quantity), 0) as total_quantity
        FROM events
        WHERE tenant = %s
    """

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sum_quantity, (tenant,))
            total_quantity = cur.fetchone()

    return total_quantity[0]


def test_ingest_is_idempotent_at_volume():
    tenant = f"test-{uuid.uuid4()}"
    start = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2026, 1, 2, tzinfo=datetime.timezone.utc)

    on_time, late = generate_events(10000, start, end, tenant=tenant)

    insert_events(on_time)
    total1 = get_total_quantity(tenant)

    insert_events(on_time)
    total2 = get_total_quantity(tenant)

    insert_events(on_time)
    total3 = get_total_quantity(tenant)

    assert total1 == total2 == total3


def get_rollup_quantity(tenant, metric, bucket_start, revision):
    rollup_quantity = """
        SELECT quantity
        FROM hourly_rollups
        WHERE tenant = %s AND metric = %s AND bucket_start = %s AND revision = %s
    """

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(rollup_quantity, (tenant, metric, bucket_start, revision))
            rollup_quantity = cur.fetchone()

    return rollup_quantity[0]


def test_late_arrival_converges():
    tenant = f"test-{uuid.uuid4()}"
    metric = "token_output"
    hour_start = datetime.datetime(2026, 1, 1, 15, 0, tzinfo=datetime.timezone.utc)
    hour_end = hour_start + datetime.timedelta(hours=1)

    on_time, late = generate_events(
        1000, hour_start, hour_end, tenant=tenant, metric=metric
    )

    insert_events(on_time)
    revision1 = recompute_hour(tenant, metric, hour_start)
    quantity1 = get_rollup_quantity(tenant, metric, hour_start, revision1)

    unique_on_time = {e["event_id"]: e["quantity"] for e in on_time}
    expected_on_time_total = sum(unique_on_time.values())
    assert quantity1 == expected_on_time_total

    insert_events(late)
    revision2 = recompute_hour(tenant, metric, hour_start)
    quantity2 = get_rollup_quantity(tenant, metric, hour_start, revision2)

    expected_total = expected_on_time_total + sum(e["quantity"] for e in late)

    assert revision2 > revision1
    assert quantity2 == expected_total


def test_recompute_is_stable_when_nothing_changed():
    tenant = f"test-{uuid.uuid4()}"
    metric = "tokens_output"
    hour_start = datetime.datetime(2026, 1, 1, 15, 0, tzinfo=datetime.timezone.utc)

    events = [
        {
            "event_id": str(uuid.uuid4()),
            "tenant": tenant,
            "metric": metric,
            "quantity": 100,
            "event_time": hour_start,
        }
    ]
    insert_events(events)

    revision1 = recompute_hour(tenant, metric, hour_start)
    revision2 = recompute_hour(tenant, metric, hour_start)

    assert revision1 == revision2
