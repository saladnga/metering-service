CREATE TABLE events (
    event_id UUID PRIMARY KEY,
    tenant TEXT NOT NULL,
    metric TEXT NOT NULL,
    quantity NUMERIC NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_events_event_time on events(event_time);

CREATE TABLE hourly_rollups (
    tenant TEXT NOT NULL,
    metric TEXT NOT NULL,
    bucket_start TIMESTAMPTZ NOT NULL,
    revision INTEGER NOT NULL,
    quantity NUMERIC NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_event_count INTEGER NOT NULL,

    PRIMARY KEY (tenant, metric, bucket_start, revision)
);

CREATE INDEX idx_hourly_rollups_lookup on hourly_rollups(tenant, metric, bucket_start, computed_at);

CREATE TABLE daily_rollups (
    tenant TEXT NOT NULL,
    metric TEXT NOT NULL,
    bucket_start TIMESTAMPTZ NOT NULL,
    revision INTEGER NOT NULL,
    quantity NUMERIC NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_event_count INTEGER NOT NULL,

    PRIMARY KEY (tenant, metric, bucket_start, revision)
);

CREATE INDEX idx_daily_rollups_lookup on daily_rollups(tenant, metric, bucket_start, computed_at);