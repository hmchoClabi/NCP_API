\set ON_ERROR_STOP on

BEGIN;

UPDATE control.tenant_report_settings AS tenant_settings
SET settings = (
    (tenant_settings.settings - 'diagram' - 'schema_version')
    || CASE
        WHEN jsonb_typeof(tenant_settings.settings -> 'sections') = 'array'
        THEN jsonb_build_object(
            'sections',
            (
                SELECT COALESCE(
                    jsonb_agg(to_jsonb(section_name) ORDER BY first_position),
                    '[]'::jsonb
                )
                FROM (
                    SELECT
                        CASE
                            WHEN section_value = 'infrastructure_diagram'
                            THEN 'infrastructure_inventory'
                            ELSE section_value
                        END AS section_name,
                        min(section_position) AS first_position
                    FROM jsonb_array_elements_text(
                        tenant_settings.settings -> 'sections'
                    ) WITH ORDINALITY AS section(
                        section_value,
                        section_position
                    )
                    GROUP BY CASE
                        WHEN section_value = 'infrastructure_diagram'
                        THEN 'infrastructure_inventory'
                        ELSE section_value
                    END
                ) AS normalized_sections
            )
        )
        ELSE '{}'::jsonb
    END
    || jsonb_build_object('schema_version', '1.1')
)
WHERE tenant_settings.settings ? 'diagram'
   OR (tenant_settings.settings -> 'sections') ? 'infrastructure_diagram'
   OR tenant_settings.settings ->> 'schema_version' = '1.0';

INSERT INTO control.schema_versions (version, description)
VALUES ('160', 'Remove report topology settings')
ON CONFLICT (version) DO UPDATE SET description = EXCLUDED.description;

COMMIT;
