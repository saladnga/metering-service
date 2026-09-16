import datetime
from metering.generate import generate_events
from metering.ingest import insert_events
from metering.rollup import recompute_hour
from metering.db import pool


def get_total(tenant, metric, hour_start):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT quantity FROM hourly_rollups
                WHERE tenant = %s AND metric = %s AND bucket_start = %s
                ORDER BY revision DESC LIMIT 1
                """,
                (tenant, metric, hour_start),
            )
            row = cur.fetchone()
            return row[0] if row else 0


def main():
    tenant = "demo"
    metric = "tokens_output"
    hour_start = datetime.datetime(2026, 1, 1, 15, 0, tzinfo=datetime.timezone.utc)
    hour_end = hour_start + datetime.timedelta(hours=1)

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM events WHERE tenant = %s", (tenant,))
            cur.execute("DELETE FROM hourly_rollups WHERE tenant = %s", (tenant,))
        conn.commit()

    print(f"Generating 10,000 events for {tenant}/{metric}...")
    on_time, late = generate_events(
        10000, hour_start, hour_end, tenant=tenant, metric=metric
    )

    accepted, duplicates = insert_events(on_time)
    print(f"Ingested on-time batch: accepted={accepted} duplicates={duplicates}")

    revision = recompute_hour(tenant, metric, hour_start)
    total_before = get_total(tenant, metric, hour_start)
    print(f"Rolled up bucket -> revision {revision}, total = {total_before}")

    accepted, duplicates = insert_events(late)
    print(
        f"Delivered {len(late)} LATE events: accepted={accepted} duplicates={duplicates}"
    )

    revision = recompute_hour(tenant, metric, hour_start)
    total_after = get_total(tenant, metric, hour_start)
    print(f"Recomputed -> revision {revision}, total = {total_after}")

    print(f"\nDifference from late arrival: {total_after - total_before}")


if __name__ == "__main__":
    main()
