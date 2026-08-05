\set ON_ERROR_STOP on

CREATE OR REPLACE VIEW control.v_msp_customer_daily_status
WITH (security_invoker = true)
AS
SELECT
    t.id AS tenant_id,
    t.customer_code,
    t.customer_name,
    t.environment,
    t.region,
    t.status AS tenant_status,
    f.fact_date,
    f.collection_status,
    f.server_count,
    f.critical_count,
    f.warning_count,
    f.info_count,
    f.activity_failure_count,
    f.collection_error_count,
    f.estimated_cost,
    f.confirmed_cost,
    f.cost_confidence,
    f.latest_report_run_id,
    f.updated_at
FROM control.tenants t
LEFT JOIN control.daily_customer_facts f
    ON f.tenant_id = t.id;

CREATE OR REPLACE VIEW control.v_report_run_status
WITH (security_invoker = true)
AS
SELECT
    r.id AS report_run_id,
    r.tenant_id,
    t.customer_code,
    t.customer_name,
    r.environment,
    r.report_type,
    r.period_start,
    r.period_end,
    r.status,
    r.trigger_type,
    r.attempt_count,
    r.error_count,
    r.queued_at,
    r.started_at,
    r.completed_at,
    CASE
        WHEN r.started_at IS NULL THEN NULL
        ELSE COALESCE(r.completed_at, clock_timestamp()) - r.started_at
    END AS execution_duration
FROM control.report_runs r
JOIN control.tenants t
    ON t.id = r.tenant_id;

CREATE OR REPLACE VIEW control.v_all_insight_events
WITH (security_invoker = true)
AS
SELECT
    e.id,
    e.report_run_id,
    e.tenant_id,
    e.environment,
    e.source_event_id,
    e.occurred_at,
    e.ended_at,
    e.severity,
    e.service_name,
    e.resource_id,
    e.resource_name,
    e.resource_type,
    e.rule_name,
    e.metric,
    e.detect_value,
    e.unit,
    e.details
FROM public_data.insight_events e
UNION ALL
SELECT
    e.id,
    e.report_run_id,
    e.tenant_id,
    e.environment,
    e.source_event_id,
    e.occurred_at,
    e.ended_at,
    e.severity,
    e.service_name,
    e.resource_id,
    e.resource_name,
    e.resource_type,
    e.rule_name,
    e.metric,
    e.detect_value,
    e.unit,
    e.details
FROM gov_data.insight_events e;

CREATE OR REPLACE VIEW control.v_event_customer_daily
WITH (security_invoker = true)
AS
SELECT
    tenant_id,
    environment,
    (occurred_at AT TIME ZONE 'Asia/Seoul')::date AS event_date_kst,
    count(*) AS event_count,
    count(*) FILTER (WHERE severity = 'CRITICAL') AS critical_count,
    count(*) FILTER (WHERE severity = 'WARNING') AS warning_count,
    count(*) FILTER (WHERE severity = 'INFO') AS info_count
FROM control.v_all_insight_events
GROUP BY
    tenant_id,
    environment,
    (occurred_at AT TIME ZONE 'Asia/Seoul')::date;

GRANT SELECT ON
    control.v_msp_customer_daily_status,
    control.v_report_run_status,
    control.v_all_insight_events,
    control.v_event_customer_daily
TO ncp_msp_app;

GRANT SELECT ON control.v_report_run_status TO ncp_control_app;

INSERT INTO control.schema_versions (version, description)
VALUES ('060', 'tenant-safe report and MSP integration views')
ON CONFLICT (version) DO UPDATE
SET description = EXCLUDED.description;
