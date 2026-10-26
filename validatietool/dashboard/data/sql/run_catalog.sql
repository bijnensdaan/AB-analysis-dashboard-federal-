-- Metadata van alle runs; dit zijn geen bij elkaar opgetelde acttellingen.
SELECT r.run_id,r.started_at,r.finished_at,r.engine_version,
 coalesce((SELECT jsonb_agg(jsonb_build_object('model',m.model_slug,'role',m.role) ORDER BY m.model_slug)
 FROM admin_burden.run_model m WHERE m.run_id=r.run_id),'[]'::jsonb) models
FROM admin_burden.extraction_run r ORDER BY r.run_id;
