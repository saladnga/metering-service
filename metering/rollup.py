from metering.db import pool
import datetime
import argparse


def recompute_hour(tenant, metric, hour_start):
    hour_end = hour_start + datetime.timedelta(hours=1)

    raw_event = """
        SELECT COALESCE(SUM(quantity), 0), COUNT(*)
        FROM events
        WHERE tenant = %s AND metric = %s AND event_time >= %s AND event_time < %s
    """

    latest_event = """
        SELECT revision, quantity, source_event_count
        FROM hourly_rollups
        WHERE tenant = %s AND metric = %s AND bucket_start = %s
        ORDER by revision DESC
        LIMIT 1
    """

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(raw_event, (tenant, metric, hour_start, hour_end))
            new_quantity, new_count = cur.fetchone()

            cur.execute(latest_event, (tenant, metric, hour_start))
            latest = cur.fetchone()
            if latest and latest[1] == new_quantity and latest[2] == new_count:
                return latest[0]
            next_revision = (latest[0] if latest else 0) + 1

            insert = """
                INSERT INTO hourly_rollups (tenant, metric, bucket_start, revision, quantity, source_event_count) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cur.execute(
                insert,
                (tenant, metric, hour_start, next_revision, new_quantity, new_count),
            )
        conn.commit()

    return next_revision


def recompute_day(tenant, metric, day_start):
    day_end = day_start + datetime.timedelta(days=1)

    aggregate_query = """
            SELECT COALESCE(SUM(quantity), 0), COUNT(*)
            FROM (
                SELECT DISTINCT ON (bucket_start) quantity
                FROM hourly_rollups
                WHERE tenant = %s AND metric = %s AND bucket_start >= %s AND bucket_start < %s
                ORDER BY bucket_start, computed_at DESC
            ) last_per_hour
        """

    latest_query = """
            SELECT revision, quantity, source_event_count
            FROM daily_rollups
            WHERE tenant = %s AND metric = %s AND bucket_start = %s
            ORDER by revision DESC
            LIMIT 1
        """

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(aggregate_query, (tenant, metric, day_start, day_end))
            new_quantity, new_count = cur.fetchone()
            cur.execute(latest_query, (tenant, metric, day_start))
            latest = cur.fetchone()

            if latest and latest[1] == new_quantity and latest[2] == new_count:
                return latest[0]
            next_revision = (latest[0] if latest else 0) + 1

            insert = """
                    INSERT INTO daily_rollups (tenant, metric, bucket_start, revision, quantity, source_event_count)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """

            cur.execute(
                insert,
                (tenant, metric, day_start, next_revision, new_quantity, new_count),
            )
        conn.commit()
    return next_revision


def reconcile(tenant, metric, day_start):
    day_end = day_start + datetime.timedelta(days=1)

    from_source_query = """
        SELECT COALESCE(SUM(quantity), 0)
        FROM events
        WHERE tenant = %s AND metric = %s AND event_time >= %s AND event_time < %s
    """

    stored_query = """
        SELECT quantity
        FROM daily_rollups
        WHERE tenant = %s AND metric = %s AND bucket_start = %s
        ORDER BY revision Desc
        LIMIT 1
    """

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(from_source_query, (tenant, metric, day_start, day_end))
            from_source = cur.fetchone()[0]
            cur.execute(stored_query, (tenant, metric, day_start))
            row = cur.fetchone()
            stored = row[0] if row else 0

    if from_source != stored:
        print(
            f"DRIFT DETECTED for {tenant}/{metric}/{day_start.date()}: "
            f"from_source={from_source} stored={stored}"
        )
        return False

    print(f"Reconciled OK for {tenant}/{metric}/{day_start.date()}: {stored}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hour", type=str)
    parser.add_argument("--backfill", type=str)
    parser.add_argument("--tenant", type=str, required=True)
    parser.add_argument("--metric", type=str, required=True)
    parser.add_argument("--reconcile", type=str)
    args = parser.parse_args()

    if args.hour:
        hour = datetime.datetime.strptime(args.hour, "%Y-%m-%dT%H").replace(
            tzinfo=datetime.timezone.utc
        )
        revision = recompute_hour(args.tenant, args.metric, hour)
        print(f"Recomputed {args.hour} -> revision {revision}")

    elif args.backfill:
        start_str, end_str = args.backfill.split("..")
        start = datetime.datetime.strptime(start_str, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc
        )
        end = datetime.datetime.strptime(end_str, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc
        )

        current = start
        while current < end:
            revision = recompute_hour(args.tenant, args.metric, current)
            print(f"Recomputed {current.isoformat()} -> revision {revision}")
            current += datetime.timedelta(hours=1)

    elif args.reconcile:
        day = datetime.datetime.strptime(args.reconcile, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc
        )
        ok = reconcile(args.tenant, args.metric, day)
        import sys

        sys.exit(0 if ok else 1)
