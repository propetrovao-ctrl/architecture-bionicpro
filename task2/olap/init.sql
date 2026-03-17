-- crm + телеметрия → витрина report_mart

CREATE TABLE IF NOT EXISTS crm_clients (
    user_id    VARCHAR(255) PRIMARY KEY,
    full_name  VARCHAR(255),
    email      VARCHAR(255),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS telemetry_raw (
    id         SERIAL PRIMARY KEY,
    user_id    VARCHAR(255) NOT NULL,
    ts         TIMESTAMP NOT NULL,
    usage_mins INTEGER DEFAULT 0,
    events     INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_telemetry_user_ts ON telemetry_raw(user_id, ts);

-- витрина по user_id (заполняет Airflow)
CREATE TABLE IF NOT EXISTS report_mart (
    id            SERIAL PRIMARY KEY,
    user_id       VARCHAR(255) NOT NULL,
    period_from   DATE NOT NULL,
    period_to     DATE NOT NULL,
    full_name     VARCHAR(255),
    email         VARCHAR(255),
    total_usage_mins INTEGER DEFAULT 0,
    total_events  INTEGER DEFAULT 0,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, period_from, period_to)
);

CREATE INDEX IF NOT EXISTS idx_report_mart_user ON report_mart(user_id);

INSERT INTO crm_clients (user_id, full_name, email) VALUES
    ('user1', 'User One', 'user1@example.com'),
    ('user2', 'User Two', 'user2@example.com'),
    ('prothetic1', 'Prothetic One', 'prothetic1@example.com'),
    ('prothetic2', 'Prothetic Two', 'prothetic2@example.com'),
    ('prothetic3', 'Prothetic Three', 'prothetic3@example.com'),
    ('admin1', 'Admin One', 'admin1@example.com')
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO telemetry_raw (user_id, ts, usage_mins, events)
SELECT 
    u.user_id,
    (CURRENT_DATE - n * interval '1 day')::timestamp,
    (20 + random() * 100)::integer,
    (5 + random() * 30)::integer
FROM (SELECT unnest(ARRAY['user1','user2','prothetic1','prothetic2','prothetic3']) AS user_id) u,
     generate_series(1, 14) n;

-- чтобы отчёт был до первого прогона DAG
INSERT INTO report_mart (user_id, period_from, period_to, full_name, email, total_usage_mins, total_events, updated_at)
SELECT c.user_id,
       (CURRENT_DATE - interval '30 days')::date,
       (CURRENT_DATE - interval '1 day')::date,
       c.full_name,
       c.email,
       COALESCE(t.total_usage_mins, 0),
       COALESCE(t.total_events, 0),
       CURRENT_TIMESTAMP
FROM crm_clients c
LEFT JOIN (
    SELECT user_id, SUM(usage_mins) AS total_usage_mins, SUM(events) AS total_events
    FROM telemetry_raw
    GROUP BY user_id
) t ON c.user_id = t.user_id
ON CONFLICT (user_id, period_from, period_to) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    email = EXCLUDED.email,
    total_usage_mins = EXCLUDED.total_usage_mins,
    total_events = EXCLUDED.total_events,
    updated_at = EXCLUDED.updated_at;
