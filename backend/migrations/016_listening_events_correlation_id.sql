-- Request/trace id for log correlation across ingestion → worker → downstream tooling.

ALTER TABLE listening_events ADD COLUMN correlation_id VARCHAR(64);

CREATE INDEX IF NOT EXISTS ix_listening_events_correlation_id
ON listening_events (correlation_id);
