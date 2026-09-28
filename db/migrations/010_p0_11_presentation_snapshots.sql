-- P0-11 immutable IPO EDGE presentation snapshot storage.
--
-- Repository definition only. Validate on a temporary Neon branch before any
-- production application. No historical checkpoint is backfilled or rewritten.

CREATE TABLE public.presentation_snapshots (
  presentation_snapshot_id bigserial PRIMARY KEY,
  presentation_contract_version text NOT NULL
    CHECK (presentation_contract_version='P0_11_PRESENTATION_V1'),
  engine text NOT NULL CHECK (engine='IPO_EDGE'),
  run_id bigint NOT NULL REFERENCES public.run_log(run_id) ON DELETE RESTRICT,
  ipo_id bigint NOT NULL REFERENCES public.ipos(ipo_id) ON DELETE RESTRICT,
  result_id text NOT NULL,
  checkpoint_id bigint NOT NULL REFERENCES public.checkpoints(checkpoint_id) ON DELETE RESTRICT,
  governance_state text NOT NULL CHECK (btrim(governance_state) <> ''),
  sections jsonb NOT NULL
    CHECK (jsonb_typeof(sections)='array' AND jsonb_array_length(sections)=4),
  source_payload_hash text NOT NULL CHECK (btrim(source_payload_hash) <> ''),
  presentation_hash text NOT NULL CHECK (presentation_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (result_id = ipo_id::text)
);

CREATE UNIQUE INDEX uq_ipo_presentation_exact_identity
ON public.presentation_snapshots(run_id,result_id,checkpoint_id);

-- A governed IPO presentation may bind only to the exact T2_FINAL_DAY checkpoint
-- of the same IPO. This closes the otherwise possible loophole of combining three
-- individually valid but unrelated IDs.
CREATE FUNCTION public.validate_p0_11_presentation_identity()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE
  checkpoint_ipo bigint;
  checkpoint_kind text;
BEGIN
  SELECT c.ipo_id,c.checkpoint_type
    INTO checkpoint_ipo,checkpoint_kind
    FROM public.checkpoints c
   WHERE c.checkpoint_id=NEW.checkpoint_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'P0-11 presentation checkpoint % does not exist', NEW.checkpoint_id
      USING ERRCODE='23503';
  END IF;
  IF checkpoint_kind <> 'T2_FINAL_DAY' THEN
    RAISE EXCEPTION 'P0-11 IPO presentation requires T2_FINAL_DAY, got %', checkpoint_kind
      USING ERRCODE='23514';
  END IF;
  IF checkpoint_ipo <> NEW.ipo_id THEN
    RAISE EXCEPTION 'P0-11 presentation IPO/checkpoint identity mismatch'
      USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER presentation_snapshots_validate_identity
BEFORE INSERT ON public.presentation_snapshots
FOR EACH ROW EXECUTE FUNCTION public.validate_p0_11_presentation_identity();

CREATE TRIGGER presentation_snapshots_reject_mutation
BEFORE UPDATE OR DELETE OR TRUNCATE ON public.presentation_snapshots
FOR EACH STATEMENT EXECUTE FUNCTION public.reject_checkpoint_mutation();
ALTER TABLE public.presentation_snapshots ENABLE ALWAYS TRIGGER presentation_snapshots_reject_mutation;

REVOKE ALL ON public.presentation_snapshots FROM PUBLIC;
GRANT SELECT, INSERT ON public.presentation_snapshots TO ipo_edge_runtime;
GRANT USAGE ON SEQUENCE public.presentation_snapshots_presentation_snapshot_id_seq TO ipo_edge_runtime;

-- No INSERT/backfill occurs here. Existing T2 checkpoints remain intact and are
-- presentation-unavailable until a contemporaneous governed snapshot is written.
