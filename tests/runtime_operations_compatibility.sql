-- Isolated test branch only, after migration 003. psql -v ON_ERROR_STOP=1.
BEGIN;
GRANT ipo_edge_runtime TO ipo_edge_owner WITH INHERIT FALSE, SET TRUE;
SET LOCAL ROLE ipo_edge_runtime;
DO $test$
DECLARE i bigint; cp bigint; o bigint; r bigint;
BEGIN
 BEGIN
  INSERT INTO public.ipos(company_name,segment,issue_open_date) VALUES ('ISOLATED_RUNTIME_COMPAT','MAINBOARD',DATE '2099-01-01') RETURNING ipo_id INTO i;
  INSERT INTO public.ipos(company_name,segment,issue_open_date) VALUES ('ISOLATED_RUNTIME_COMPAT','MAINBOARD',DATE '2099-01-01') ON CONFLICT(company_name,issue_open_date) DO UPDATE SET status='DISCOVERED';
  INSERT INTO public.checkpoints(ipo_id,checkpoint_type,checkpoint_time,grade,decision,framework_version) VALUES(i,'INTERMEDIATE',now(),'NV','ISOLATED_RUNTIME_COMPAT','1.1') RETURNING checkpoint_id INTO cp;
  INSERT INTO public.research_evidence(ipo_id,checkpoint_id,research_block,field_name,source_url,retrieved_at,verification_status) VALUES(i,cp,'R1_BUSINESS','fixture','https://example.invalid/test',now(),'NOT_VERIFIED');
  INSERT INTO public.subscription_snapshots(ipo_id,captured_at,source_url) VALUES(i,now(),'https://example.invalid/test');
  INSERT INTO public.market_sentiment_snapshots(ipo_id,captured_at,source_url) VALUES(i,now(),'https://example.invalid/test');
  INSERT INTO public.listing_outcomes(ipo_id,issue_price,listing_price,listing_gain_percent,listing_date,source_url) VALUES(i,100,100,0,DATE '2099-01-02','https://example.invalid/test') RETURNING outcome_id INTO o;
  INSERT INTO public.listing_outcomes(ipo_id,issue_price,listing_price,listing_gain_percent,listing_date,source_url) VALUES(i,100,100,0,DATE '2099-01-02','https://example.invalid/test') ON CONFLICT(ipo_id) DO UPDATE SET listing_price=EXCLUDED.listing_price;
  INSERT INTO public.assessments(ipo_id,canonical_checkpoint_id,outcome_id,classification) VALUES(i,cp,o,'CORRECT_AVOIDANCE');
  INSERT INTO public.assessments(ipo_id,canonical_checkpoint_id,outcome_id,classification) VALUES(i,cp,o,'CORRECT_AVOIDANCE') ON CONFLICT(ipo_id) DO UPDATE SET classification=EXCLUDED.classification;
  INSERT INTO public.efficacy_snapshots(as_of_date,framework_version) VALUES(DATE '2099-01-02','1.1');
  UPDATE public.efficacy_snapshots SET universe_count=1 WHERE as_of_date=DATE '2099-01-02' AND framework_version='1.1';
  INSERT INTO public.learnings(origin_ipo_id,hypothesis,observed_signal,status) VALUES(i,'fixture','fixture','TESTING');
  INSERT INTO public.run_log(run_type,framework_version) VALUES('MANUAL','1.1') RETURNING run_id INTO r;
  UPDATE public.run_log SET status='COMPLETED',completed_at=now() WHERE run_id=r;
  PERFORM * FROM public.framework_versions;
  PERFORM * FROM public.learnings;
  RAISE EXCEPTION 'Rollback all fixtures' USING ERRCODE='P9001';
 EXCEPTION WHEN SQLSTATE 'P9001' THEN NULL;
 END;
END $test$;
RESET ROLE;
REVOKE ipo_edge_runtime FROM ipo_edge_owner;
ROLLBACK;
