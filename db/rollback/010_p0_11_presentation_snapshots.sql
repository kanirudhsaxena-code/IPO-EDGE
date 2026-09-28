-- Safe rollback for P0-11 schema validation only.
-- Once any immutable presentation snapshot exists, rollback fails closed rather
-- than deleting historical evidence.
DO $$
BEGIN
  IF to_regclass('public.presentation_snapshots') IS NOT NULL
     AND EXISTS (SELECT 1 FROM public.presentation_snapshots LIMIT 1) THEN
    RAISE EXCEPTION 'P0-11 rollback blocked: immutable presentation snapshots already exist'
      USING ERRCODE='55000';
  END IF;
END;
$$;

DROP TABLE IF EXISTS public.presentation_snapshots;
DROP FUNCTION IF EXISTS public.validate_p0_11_presentation_identity();
