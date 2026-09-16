import random
import datetime
import uuid


def generate_events(n, start, end, tenant="acme", metric="tokens_output", seed=42):
    rng = random.Random(seed)
    gap_second = (end - start).total_seconds()

    events = []
    for _ in range(n):
        offset_seconds = rng.uniform(0, gap_second)
        event_time = start + datetime.timedelta(seconds=offset_seconds)
        event = {
            "event_id": str(uuid.uuid4()),
            "tenant": tenant,
            "metric": metric,
            "quantity": rng.randint(1, 100),
            "event_time": event_time,
        }
        events.append(event)
        
    num_late = round(0.03 * len(events))    
    late_sample = rng.sample(events, k=num_late)
    late_ids = {e["event_id"] for e in late_sample}
    
    late_events = [e for e in events if e["event_id"] in late_ids]
    on_time_events = [e for e in events if e["event_id"] not in late_ids]
        
    num_duplicates = round(0.05 * len(on_time_events))
    duplicates = rng.sample(on_time_events, k=num_duplicates)    
    on_time_events += duplicates
    
    rng.shuffle(on_time_events)
    
    return on_time_events, late_events
