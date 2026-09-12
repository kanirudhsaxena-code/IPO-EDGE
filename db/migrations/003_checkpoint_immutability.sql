-- Apply as the table owner inside one transaction; no checkpoint data changes.
SET LOCAL lock_timeout = '5s';
LOCK TABLE public.checkpoints IN ACCESS EXCLUSIVE MODE;

CREATE FUNCTION public.reject_checkpoint_mutation()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  RAISE EXCEPTION 'IPO EDGE checkpoints are append-only: % is forbidden', TG_OP
    USING ERRCODE = '55000';
END;
$$;

-- Replace silent rewrite rules atomically with explicit errors.
DROP RULE checkpoints_no_update ON public.checkpoints;
DROP RULE checkpoints_no_delete ON public.checkpoints;
CREATE TRIGGER checkpoints_reject_mutation
BEFORE UPDATE OR DELETE OR TRUNCATE ON public.checkpoints
FOR EACH STATEMENT EXECUTE FUNCTION public.reject_checkpoint_mutation();
ALTER TABLE public.checkpoints ENABLE ALWAYS TRIGGER checkpoints_reject_mutation;

-- Capability role: no login or owning-role membership. Credentials are a separate cutover.
CREATE ROLE ipo_edge_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT CONNECT ON DATABASE ipo_edge TO ipo_edge_runtime;
GRANT USAGE ON SCHEMA public TO ipo_edge_runtime;
REVOKE ALL ON public.checkpoints FROM PUBLIC;
GRANT SELECT, INSERT ON public.checkpoints TO ipo_edge_runtime;
GRANT USAGE ON SEQUENCE public.checkpoints_checkpoint_id_seq TO ipo_edge_runtime;

-- Existing operational write paths; no version registration rights.
GRANT SELECT ON public.framework_versions, public.ipos, public.research_evidence,
 public.subscription_snapshots, public.market_sentiment_snapshots, public.listing_outcomes,
 public.assessments, public.learnings, public.efficacy_snapshots, public.run_log TO ipo_edge_runtime;
GRANT INSERT ON public.ipos, public.research_evidence, public.subscription_snapshots,
 public.market_sentiment_snapshots, public.listing_outcomes, public.assessments,
 public.learnings, public.efficacy_snapshots, public.run_log TO ipo_edge_runtime;
GRANT UPDATE ON public.ipos, public.listing_outcomes, public.assessments,
 public.efficacy_snapshots, public.run_log TO ipo_edge_runtime;
GRANT USAGE ON SEQUENCE public.ipos_ipo_id_seq, public.research_evidence_evidence_id_seq,
 public.subscription_snapshots_snapshot_id_seq, public.market_sentiment_snapshots_snapshot_id_seq,
 public.listing_outcomes_outcome_id_seq, public.assessments_assessment_id_seq,
 public.learnings_learning_id_seq, public.efficacy_snapshots_efficacy_id_seq,
 public.run_log_run_id_seq TO ipo_edge_runtime;
-- Learning adoption remains an administrator operation.
