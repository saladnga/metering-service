from metering.db import pool


def insert_events(events: list[dict]):
    if not events:
        return 0, 0
    
    placeholder_groups = []
    params = []
    
    for event in events:
        placeholder_groups.append("(%s, %s, %s, %s, %s)")
        params.append(event["event_id"])
        params.append(event["tenant"])
        params.append(event["metric"])
        params.append(event["quantity"])
        params.append(event["event_time"])
    
    values = ", ".join(placeholder_groups)
    
    statement = f"""
        INSERT INTO events (event_id, tenant, metric, quantity, event_time) 
        VALUES {values}
        ON CONFLICT (event_id) DO NOTHING 
        RETURNING event_id
    """
    
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(statement, params)
            inserted_ids = cur.fetchall()
            accepted = len(inserted_ids)
        conn.commit()
    
    duplicates = len(events) - accepted
    
    return (accepted, duplicates)

