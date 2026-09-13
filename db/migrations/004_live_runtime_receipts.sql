-- Apply once, transactionally. No historical table contents are modified.
CREATE TABLE public.runtime_receipts (
  event_key text PRIMARY KEY,
  kind text NOT NULL CHECK (kind IN ('DISCOVERY','RESEARCH','OUTCOME','LEARNING','VALIDATION','INTEGRITY')),
  ipo_id bigint REFERENCES public.ipos(ipo_id),
  run_id bigint NOT NULL REFERENCES public.run_log(run_id),
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX runtime_receipts_ipo_kind ON public.runtime_receipts(ipo_id,kind,created_at DESC);
CREATE TRIGGER runtime_receipts_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
ON public.runtime_receipts FOR EACH STATEMENT EXECUTE FUNCTION public.reject_checkpoint_mutation();
ALTER TABLE public.runtime_receipts ENABLE ALWAYS TRIGGER runtime_receipts_immutable;
GRANT SELECT, INSERT ON public.runtime_receipts TO ipo_edge_runtime;
