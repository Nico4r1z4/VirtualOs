-- Job progress reporting + at most ONE active job per (workspace, kind).
--
-- Why: users clicking a paid action repeatedly (or the mascot + a button at the
-- same time) queued duplicate jobs, each spending Apify/LLM money. The partial
-- unique index makes duplicates impossible at the database level, race-free;
-- the queue returns the already-active job instead of creating another.

ALTER TABLE vos.jobs
    ADD COLUMN IF NOT EXISTS progress JSONB NOT NULL DEFAULT '{}';

-- Collapse any pre-existing active duplicates before adding the constraint
-- (keep the oldest active job per workspace+kind).
UPDATE vos.jobs j SET status = 'failed', finished_at = NOW(),
       error = 'superseded: duplicate active job (migration 0002)'
WHERE j.status IN ('pending', 'running')
  AND EXISTS (
      SELECT 1 FROM vos.jobs o
      WHERE o.workspace_id = j.workspace_id AND o.kind = j.kind
        AND o.status IN ('pending', 'running')
        AND (o.created_at, o.id) < (j.created_at, j.id)
  );

CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_one_active_per_kind
    ON vos.jobs (workspace_id, kind)
    WHERE status IN ('pending', 'running');

CREATE INDEX IF NOT EXISTS idx_jobs_ws_created
    ON vos.jobs (workspace_id, created_at DESC);
