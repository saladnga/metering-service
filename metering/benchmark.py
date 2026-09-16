"""
Benchmark the deployed API over the real network — not local imports. Ingestion throughput, duplicate rejection, and p95 query latency.
"""

import datetime
import time

import requests

from metering.generate import generate_events

BASE_URL = "http://3.80.38.175:8000"
TENANT = "benchmark"
METRIC = "tokens_output"
BATCH_SIZE = 1000


def event_to_payload(event):
    return {
        "event_id": str(event["event_id"]),
        "tenant": event["tenant"],
        "metric": event["metric"],
        "quantity": event["quantity"],
        "event_time": event["event_time"].isoformat(),
    }


def main():
    start = datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2026, 6, 2, tzinfo=datetime.timezone.utc)

    print(f"Generating 50,000 events for {TENANT}/{METRIC}...")
    on_time, late = generate_events(50000, start, end, tenant=TENANT, metric=METRIC)

    # 1. Ingestion throughput
    total_accepted, total_duplicates = 0, 0
    last_batch_payload = None
    t0 = time.time()
    for i in range(0, len(on_time), BATCH_SIZE):
        batch = on_time[i : i + BATCH_SIZE]
        payload = [event_to_payload(e) for e in batch]
        r = requests.post(f"{BASE_URL}/v1/events", json=payload)
        r.raise_for_status()
        result = r.json()
        total_accepted += result["accepted"]
        total_duplicates += result["duplicates"]
        last_batch_payload = payload
    elapsed = time.time() - t0

    print(f"\n--- Ingestion throughput ---")
    print(f"{len(on_time)} events sent in {elapsed:.1f}s -> {len(on_time) / elapsed:.0f} events/sec")
    print(f"accepted={total_accepted} duplicates={total_duplicates}")

    # 2. Duplicate rejection: resend the last batch unchanged
    r = requests.post(f"{BASE_URL}/v1/events", json=last_batch_payload)
    r.raise_for_status()
    print(f"\n--- Duplicate rejection (resend last batch of {len(last_batch_payload)}) ---")
    print(r.json())

    # 3. p95 query latency
    latencies_ms = []
    for _ in range(30):
        t0 = time.time()
        r = requests.get(
            f"{BASE_URL}/v1/usage",
            params={
                "tenant": TENANT,
                "metric": METRIC,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )
        r.raise_for_status()
        latencies_ms.append((time.time() - t0) * 1000)

    latencies_ms.sort()
    p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
    p50 = latencies_ms[len(latencies_ms) // 2]

    print(f"\n--- Query latency (GET /v1/usage, {len(latencies_ms)} requests) ---")
    print(f"p50 = {p50:.1f}ms  p95 = {p95:.1f}ms")


if __name__ == "__main__":
    main()
