-- ISOLATED NEON TEST BRANCH ONLY. Requires migration 003.
-- Run with psql -v ON_ERROR_STOP=1; every fixture and temporary grant is rolled back.
BEGIN;
DO $test$
DECLARE command text; blocked boolean; fixture_id bigint;
BEGIN
  IF (SELECT count(*) FROM public.checkpoints WHERE framework_version='1.0') <> 123
    OR (SELECT md5(string_agg(to_jsonb(c)::text,E'\n' ORDER BY checkpoint_id))
        FROM public.checkpoints c WHERE framework_version='1.0')
       IS DISTINCT FROM '5df3c7fc2ce6e3556a523ddfa03d32fb'
  THEN RAISE EXCEPTION 'Historical baseline mismatch'; END IF;
  FOREACH command IN ARRAY ARRAY[
    'UPDATE public.checkpoints SET decision=decision',
    'DELETE FROM public.checkpoints',
    'TRUNCATE public.checkpoints CASCADE'
  ] LOOP
    blocked := false;
    BEGIN EXECUTE command;
    EXCEPTION WHEN SQLSTATE '55000' THEN blocked := true;
    END;
    IF NOT blocked THEN RAISE EXCEPTION 'Mutation was not explicitly blocked: %',command; END IF;
  END LOOP;
  BEGIN
    INSERT INTO public.checkpoints (ipo_id,checkpoint_type,checkpoint_time,grade,decision,framework_version)
    SELECT ipo_id,'INTERMEDIATE',clock_timestamp(),'NV','ISOLATED_TEST','1.1'
    FROM public.ipos ORDER BY ipo_id LIMIT 1 RETURNING checkpoint_id INTO fixture_id;
    IF fixture_id IS NULL THEN RAISE EXCEPTION 'Insert failed'; END IF;
    RAISE EXCEPTION 'Rollback fixture' USING ERRCODE='P9001';
  EXCEPTION WHEN SQLSTATE 'P9001' THEN NULL; END;
END $test$;
GRANT ipo_edge_runtime TO ipo_edge_owner WITH INHERIT FALSE, SET TRUE;
SET LOCAL ROLE ipo_edge_runtime;
DO $test$
DECLARE command text; blocked boolean; fixture_id bigint;
BEGIN
  IF (SELECT count(*) FROM public.checkpoints WHERE framework_version='1.0') <> 123
    OR (SELECT md5(string_agg(to_jsonb(c)::text,E'\n' ORDER BY checkpoint_id))
        FROM public.checkpoints c WHERE framework_version='1.0')
       IS DISTINCT FROM '5df3c7fc2ce6e3556a523ddfa03d32fb'
  THEN RAISE EXCEPTION 'Historical baseline mismatch'; END IF;
  FOREACH command IN ARRAY ARRAY[
    'UPDATE public.checkpoints SET decision=decision',
    'DELETE FROM public.checkpoints',
    'TRUNCATE public.checkpoints CASCADE'
  ] LOOP
    blocked := false;
    BEGIN EXECUTE command;
    EXCEPTION WHEN SQLSTATE '42501' THEN blocked := true;
    END;
    IF NOT blocked THEN RAISE EXCEPTION 'Mutation was not explicitly blocked: %',command; END IF;
  END LOOP;
  BEGIN
    INSERT INTO public.checkpoints (ipo_id,checkpoint_type,checkpoint_time,grade,decision,framework_version)
    SELECT ipo_id,'INTERMEDIATE',clock_timestamp(),'NV','ISOLATED_TEST','1.1'
    FROM public.ipos ORDER BY ipo_id LIMIT 1 RETURNING checkpoint_id INTO fixture_id;
    IF fixture_id IS NULL THEN RAISE EXCEPTION 'Insert failed'; END IF;
    RAISE EXCEPTION 'Rollback fixture' USING ERRCODE='P9001';
  EXCEPTION WHEN SQLSTATE 'P9001' THEN NULL; END;
END $test$;
RESET ROLE;
REVOKE ipo_edge_runtime FROM ipo_edge_owner;
ROLLBACK;
