-- Persistent per-line crossing counters, incremented on every line_cross event.
-- line_id stores the line NAME (the identifier carried in AI events), with the
-- line UUID kept when resolvable for joins.
CREATE TABLE IF NOT EXISTS line_counters (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    camera_id   UUID REFERENCES cameras(id) ON DELETE CASCADE,
    line_id     TEXT NOT NULL,
    count_in    BIGINT NOT NULL DEFAULT 0,
    count_out   BIGINT NOT NULL DEFAULT 0,
    count_total BIGINT NOT NULL DEFAULT 0,
    last_class  TEXT NOT NULL DEFAULT '',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, camera_id, line_id)
);

CREATE INDEX IF NOT EXISTS idx_line_counters_org_cam ON line_counters (org_id, camera_id);
