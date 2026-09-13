CREATE FUNCTION public.apply_ipo_edge_outcome(p_ipo_id bigint, p_observations jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE o jsonb; reference jsonb; issue numeric; listing numeric; gain numeric; listed date; count_sources int;
  outcomeid bigint; runid bigint; final public.checkpoints%ROWTYPE; class text;
BEGIN
  PERFORM pg_advisory_xact_lock(741103);
  IF EXISTS(SELECT 1 FROM public.listing_outcomes WHERE ipo_id=p_ipo_id) THEN RETURN jsonb_build_object('status','ALREADY_RECORDED'); END IF;
  IF jsonb_typeof(p_observations) IS DISTINCT FROM 'array' OR jsonb_array_length(p_observations)<2 THEN RAISE EXCEPTION 'Two verified listing sources required'; END IF;
  SELECT count(DISTINCT regexp_replace(regexp_replace(a->>'source_url','^https://(www\.)?([^/]+).*$', '\2'), '^(archives|www)\.', '')) INTO count_sources
    FROM jsonb_array_elements(p_observations) a WHERE a->>'source_url' LIKE 'https://%';
  IF count_sources<2 THEN RAISE EXCEPTION 'Listing sources must be independent'; END IF;
  reference:=p_observations->0; issue:=(reference->>'issue_price')::numeric; listing:=(reference->>'listing_price')::numeric; listed:=(reference->>'listing_date')::date;
  IF issue IS NULL OR listing IS NULL OR listed IS NULL OR issue::text IN ('NaN','Infinity','-Infinity') OR listing::text IN ('NaN','Infinity','-Infinity') OR issue<=0 OR listing<0 OR listed>(clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date THEN RAISE EXCEPTION 'Invalid listing prices or date'; END IF;
  IF NOT EXISTS(SELECT 1 FROM public.ipos WHERE ipo_id=p_ipo_id AND issue_close_date<listed) THEN RAISE EXCEPTION 'Listing cannot precede issue closure'; END IF;
  FOR o IN SELECT * FROM jsonb_array_elements(p_observations) LOOP
    IF o->>'verified' IS DISTINCT FROM 'true' OR o->>'source_url' IS NULL OR o->>'source_url' NOT LIKE 'https://%'
      OR o->>'retrieved_at' IS NULL OR (o->>'retrieved_at')::timestamptz>clock_timestamp()
      OR (o->>'listing_date')::date IS DISTINCT FROM listed
      OR (o->>'issue_price')::numeric IS NULL OR (o->>'listing_price')::numeric IS NULL
      OR (o->>'issue_price')::numeric::text IN ('NaN','Infinity','-Infinity') OR (o->>'listing_price')::numeric::text IN ('NaN','Infinity','-Infinity')
      OR abs((o->>'issue_price')::numeric-issue)>.02 OR abs((o->>'listing_price')::numeric-listing)>.02 THEN RAISE EXCEPTION 'Listing evidence conflict'; END IF;
  END LOOP;
  gain:=round((listing/issue-1)*100,2);
  INSERT INTO public.run_log(run_type,framework_version) VALUES('LISTING_OUTCOME','1.1') RETURNING run_id INTO runid;
  INSERT INTO public.listing_outcomes(ipo_id,issue_price,listing_price,listing_gain_percent,listing_date,source_url)
    VALUES(p_ipo_id,issue,listing,gain,listed,reference->>'source_url') RETURNING outcome_id INTO outcomeid;
  SELECT * INTO final FROM public.checkpoints WHERE ipo_id=p_ipo_id AND checkpoint_type='T2_FINAL_DAY'
    AND (checkpoint_time AT TIME ZONE 'Asia/Kolkata')::date<listed ORDER BY checkpoint_time DESC LIMIT 1;
  IF final.checkpoint_id IS NOT NULL THEN
    class:=CASE WHEN final.grade IN ('A+','A++') AND gain>=20 THEN 'STRONG_HIT'
      WHEN final.grade IN ('A+','A++') AND gain>=0 THEN 'MODERATE_HIT'
      WHEN final.grade IN ('A+','A++') THEN 'FALSE_POSITIVE' WHEN gain>=20 THEN 'MISSED_OPPORTUNITY' ELSE 'CORRECT_AVOIDANCE' END;
    INSERT INTO public.assessments(ipo_id,canonical_checkpoint_id,outcome_id,classification,is_missed_opportunity,forecast_error_pp)
      VALUES(p_ipo_id,final.checkpoint_id,outcomeid,class,class='MISSED_OPPORTUNITY',abs(gain-final.base_gain_estimate)) ON CONFLICT(ipo_id) DO NOTHING;
    IF final.framework_version='1.1' AND class IN ('FALSE_POSITIVE','MISSED_OPPORTUNITY') THEN
      INSERT INTO public.learnings(origin_ipo_id,hypothesis,observed_signal,status,proposed_change)
        VALUES(p_ipo_id,'Test pre-listing evidence coverage and institutional-demand calibration for '||class,
          'Frozen V1.1 checkpoint '||final.checkpoint_id||'; actual gain '||gain||'%', 'TESTING',
          'Test on chronologically separated development and validation cohorts; propose changes only. No automatic adoption.');
      INSERT INTO public.runtime_receipts(event_key,kind,ipo_id,run_id,payload)
        VALUES('learning:1.1:'||final.checkpoint_id||':'||class,'LEARNING',p_ipo_id,runid,jsonb_build_object('classification',class));
    END IF;
  END IF;
  INSERT INTO public.runtime_receipts(event_key,kind,ipo_id,run_id,payload) VALUES('outcome:'||p_ipo_id,'OUTCOME',p_ipo_id,runid,jsonb_build_object('observations',p_observations));
  UPDATE public.run_log SET status='COMPLETED',completed_at=clock_timestamp(),outcomes_added=1 WHERE run_id=runid;
  RETURN jsonb_build_object('status','RECORDED','outcome_id',outcomeid,'classification',class,'listing_gain',gain,'run_id',runid);
END;
$$;
REVOKE ALL ON FUNCTION public.apply_ipo_edge_outcome(bigint,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.apply_ipo_edge_outcome(bigint,jsonb) TO ipo_edge_runtime;
