-- Restore previous intake without deleting historical or operational data.
-- Narrow, validated entry point for scheduled ChatGPT research through the existing Neon connector.
-- No API key, new credential or external model provider is required.
CREATE OR REPLACE FUNCTION public.apply_ipo_edge_research(p_ipo_id bigint, p_bundle jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE
  stamp timestamptz := clock_timestamp(); local_day date := (stamp AT TIME ZONE 'Asia/Kolkata')::date;
  ipo public.ipos%ROWTYPE; framework public.framework_versions%ROWTYPE;
  previous public.checkpoints%ROWTYPE; cp_type text; cp_id bigint; runid bigint;
  block text; component text; e jsonb; estimate jsonb; score numeric:=0; value numeric;
  critical_ok boolean:=true; lane boolean:=false; grade text; decision text; blocker text;
  signature text; previous_signature text; source_count int; payload jsonb;
BEGIN
  PERFORM pg_advisory_xact_lock(741103);
  SELECT * INTO STRICT ipo FROM public.ipos WHERE ipo_id=p_ipo_id;
  SELECT * INTO STRICT framework FROM public.framework_versions WHERE version='1.1' AND status='FROZEN';
  IF stamp<framework.effective_at OR NOT coalesce((framework.rules_config->>'production_activation_approved')::boolean,false) THEN
    RAISE EXCEPTION 'V1.1 not active'; END IF;
  IF jsonb_typeof(p_bundle->'evidence') IS DISTINCT FROM 'array'
     OR jsonb_typeof(p_bundle->'scores') IS DISTINCT FROM 'object'
     OR p_bundle->>'research_complete' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'Complete research bundle required'; END IF;
  FOR block IN SELECT 'R'||i FROM generate_series(1,8) i LOOP
    IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(p_bundle->'evidence') a WHERE a->>'block'=block) THEN
      RAISE EXCEPTION 'Missing research block %',block; END IF;
  END LOOP;
  FOR e IN SELECT * FROM jsonb_array_elements(p_bundle->'evidence') LOOP
    IF e->>'block' NOT IN ('R1','R2','R3','R4','R5','R6','R7','R8') THEN RAISE EXCEPTION 'Unknown block'; END IF;
    IF e->>'retrieved_at' IS NULL OR (e->>'retrieved_at')::timestamptz>stamp
       OR (e->>'published_at')::timestamptz>stamp THEN RAISE EXCEPTION 'Missing or future evidence timestamp'; END IF;
    IF e->>'source_url' !~ '^https://' OR e->>'source_url' IS NULL THEN RAISE EXCEPTION 'Source URL required'; END IF;
    IF e->>'verified'='true' AND (e->'values' IS NULL OR e->'values' IN ('null'::jsonb,'{}'::jsonb)) THEN
      RAISE EXCEPTION 'Verified evidence requires source-grounded values'; END IF;
  END LOOP;
  FOREACH block IN ARRAY ARRAY['R2','R3','R4','R6','R7'] LOOP
    IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(p_bundle->'evidence') a WHERE a->>'block'=block AND a->>'verified'='true') THEN critical_ok:=false; END IF;
  END LOOP;
  IF NOT critical_ok THEN
    SELECT count(DISTINCT regexp_replace(regexp_replace(a->>'source_url','^https://(www\.)?([^/]+).*$', '\2'), '^(archives|www)\.', '')) INTO source_count
    FROM jsonb_array_elements(coalesce(p_bundle->'attempts','[]'::jsonb)) a WHERE a->>'source_url' LIKE 'https://%';
    IF source_count<2 THEN RAISE EXCEPTION 'Two independent source attempts required before NV'; END IF;
  END IF;
  FOR component,value IN SELECT key,(val #>> '{}')::numeric FROM jsonb_each(p_bundle->'scores') AS t(key,val) WHERE val<>'null'::jsonb LOOP
    IF NOT framework.scoring_config ? component OR value<0 OR value>1 OR value::text IN ('NaN','Infinity','-Infinity') THEN RAISE EXCEPTION 'Invalid component score'; END IF;
    score:=score+value*(framework.scoring_config->>component)::numeric;
  END LOOP;
  blocker:=nullif(p_bundle->>'hard_blocker','');
  IF EXISTS(SELECT 1 FROM jsonb_array_elements(p_bundle->'evidence') a WHERE a->>'verification_status'='CONFLICT') THEN blocker:='CONFLICTING_EVIDENCE'; END IF;
  IF NOT critical_ok OR blocker IS NOT NULL THEN
    score:=NULL; grade:='NV'; decision:='NO_ACTION'; blocker:=coalesce(blocker,'CRITICAL_EVIDENCE_NOT_VERIFIED');
  ELSE
    score:=round(score,2);
    IF score>=95 THEN grade:='A++';decision:='STRONG_SUBSCRIBE';
    ELSIF score>=90 THEN grade:='A+';decision:='SUBSCRIBE';
    ELSIF score>=85 THEN grade:='A';decision:='TRACK'; ELSE grade:='REJECT';decision:='REJECT'; END IF;
    lane:=coalesce((p_bundle->'scores'->>'institutional_conviction')::numeric>=0.85 AND (p_bundle->'scores'->>'market_demand')::numeric>=0.80,false);
  END IF;
  SELECT * INTO previous FROM public.checkpoints WHERE ipo_id=p_ipo_id ORDER BY checkpoint_time DESC,checkpoint_id DESC LIMIT 1;
  IF EXISTS(SELECT 1 FROM public.checkpoints WHERE ipo_id=p_ipo_id AND checkpoint_type='T2_FINAL_DAY') THEN
    RETURN jsonb_build_object('status','ALREADY_FINAL','ipo_id',p_ipo_id); END IF;
  IF ipo.status IN ('WITHDRAWN','CANCELLED') THEN RETURN jsonb_build_object('status','INACTIVE_ISSUE'); END IF;
  IF ipo.issue_close_date IS NULL OR local_day>ipo.issue_close_date OR local_day>=ipo.listing_date THEN
    RETURN jsonb_build_object('status','NO_RETROSPECTIVE_CHECKPOINT','ipo_id',p_ipo_id); END IF;
  cp_type:=CASE WHEN local_day=ipo.issue_close_date AND (stamp AT TIME ZONE 'Asia/Kolkata')::time>=time '19:00'
    THEN 'T2_FINAL_DAY' WHEN previous.checkpoint_id IS NULL THEN 'T1_DISCOVERY' ELSE 'INTERMEDIATE' END;
  IF cp_type='T2_FINAL_DAY' AND p_bundle->>'subscription_is_final' IS DISTINCT FROM 'true' THEN
    RETURN jsonb_build_object('status','FINAL_SUBSCRIPTION_NOT_VERIFIED','ipo_id',p_ipo_id); END IF;
  estimate:=p_bundle->'estimates';
  IF estimate IS NOT NULL AND estimate<>'null'::jsonb THEN
    FOR component IN SELECT unnest(ARRAY['bear','base','bull','confidence']) LOOP
      IF estimate->>component IS NULL OR (estimate->>component)::numeric::text IN ('NaN','Infinity','-Infinity') THEN RAISE EXCEPTION 'Finite forecast values required'; END IF;
    END LOOP;
    IF NOT (estimate ?& ARRAY['bear','base','bull','confidence','method','source_urls'])
      OR jsonb_array_length(estimate->'source_urls')=0 OR coalesce(estimate->>'method','')=''
      OR (estimate->>'bear')::numeric>(estimate->>'base')::numeric OR (estimate->>'base')::numeric>(estimate->>'bull')::numeric
      OR (estimate->>'confidence')::numeric NOT BETWEEN 0 AND 1 THEN RAISE EXCEPTION 'Invalid evidence-based forecast'; END IF;
  END IF;
  signature:=md5(jsonb_build_object('scores',p_bundle->'scores','coverage',critical_ok,'blocker',blocker,'estimate',estimate,
    'evidence',(SELECT jsonb_agg(a-'retrieved_at' ORDER BY a->>'block',a->>'source_url') FROM jsonb_array_elements(p_bundle->'evidence') a))::text);
  IF previous.checkpoint_id IS NOT NULL THEN previous_signature:=(previous.evidence_delta_summary::jsonb)->>'agent_signature'; END IF;
  IF previous_signature=signature AND cp_type<>'T2_FINAL_DAY' THEN RETURN jsonb_build_object('status','UNCHANGED','ipo_id',p_ipo_id); END IF;
  INSERT INTO public.run_log(run_type,framework_version) VALUES('REASSESSMENT','1.1') RETURNING run_id INTO runid;
  payload:=jsonb_build_object('agent_signature',signature,'candidate',lane,'scores',p_bundle->'scores','previous_grade',previous.grade,
    'provider','research_agent','grade',grade,'decision',decision,'coverage_verified',critical_ok,'unresolved',p_bundle->'unresolved');
  INSERT INTO public.checkpoints(ipo_id,checkpoint_type,checkpoint_time,score,grade,decision,hard_blocker,evidence_delta_summary,framework_version,
    bear_gain_estimate,base_gain_estimate,bull_gain_estimate,confidence)
  VALUES(p_ipo_id,cp_type,stamp,score,grade,decision,blocker,payload::text,'1.1',(estimate->>'bear')::numeric,(estimate->>'base')::numeric,
    (estimate->>'bull')::numeric,100*(estimate->>'confidence')::numeric) RETURNING checkpoint_id INTO cp_id;
  FOR e IN SELECT * FROM jsonb_array_elements(p_bundle->'evidence') LOOP
    INSERT INTO public.research_evidence(ipo_id,checkpoint_id,research_block,field_name,value_text,source_url,published_at,retrieved_at,verification_status)
    VALUES(p_ipo_id,cp_id,CASE e->>'block' WHEN 'R1' THEN 'R1_BUSINESS' WHEN 'R2' THEN 'R2_FINANCIALS' WHEN 'R3' THEN 'R3_VALUATION'
      WHEN 'R4' THEN 'R4_PROMOTER_ISSUE' WHEN 'R5' THEN 'R5_ANALYST' WHEN 'R6' THEN 'R6_INSTITUTIONAL' WHEN 'R7' THEN 'R7_DEMAND' ELSE 'R8_ENVIRONMENT' END,
      'agent_review',e::text,e->>'source_url',(e->>'published_at')::timestamptz,(e->>'retrieved_at')::timestamptz,
      CASE WHEN e->>'verified'='true' THEN 'VERIFIED' ELSE 'NOT_VERIFIED' END);
  END LOOP;
  INSERT INTO public.runtime_receipts(event_key,kind,ipo_id,run_id,payload) VALUES('agent:'||cp_id,'RESEARCH',p_ipo_id,runid,
    jsonb_build_object('provider','research_agent','bundle',p_bundle,'checkpoint_id',cp_id));
  UPDATE public.run_log SET status='COMPLETED',completed_at=clock_timestamp(),researched_count=1,checkpoint_count=1 WHERE run_id=runid;
  RETURN jsonb_build_object('status','RECORDED','checkpoint_id',cp_id,'checkpoint_type',cp_type,'grade',grade,'score',score,'candidate',lane,'run_id',runid);
END;
$$;
REVOKE ALL ON FUNCTION public.apply_ipo_edge_research(bigint,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.apply_ipo_edge_research(bigint,jsonb) TO ipo_edge_runtime;

-- New validator functions may remain unused; no destructive rollback required.
