-- Function-only execution hardening. No tables, enum changes or historical updates.
CREATE FUNCTION public.validate_ipo_edge_recovery(b jsonb)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE block text; n int;
BEGIN
  FOREACH block IN ARRAY ARRAY['R2','R3','R4','R6','R7'] LOOP
    IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(b->'evidence') e WHERE e->>'block'=block AND e->>'verified'='true') THEN
      SELECT count(DISTINCT a->>'provenance_group') INTO n FROM jsonb_array_elements(coalesce(b->'attempts','[]'::jsonb)) a
      WHERE a->>'block'=block AND a->>'source_url' LIKE 'https://%'
        AND length(trim(a->>'provenance_group'))>0 AND length(trim(a->>'independence_basis'))>0
        AND length(trim(a->>'result'))>0 AND a->>'retrieved_at' IS NOT NULL
        AND (a->>'retrieved_at')::timestamptz<=clock_timestamp();
      IF n<2 THEN RAISE EXCEPTION 'RECOVERY_INCOMPLETE:%',block; END IF;
    END IF;
  END LOOP;
END $$;
REVOKE ALL ON FUNCTION public.validate_ipo_edge_recovery(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.validate_ipo_edge_recovery(jsonb) TO ipo_edge_runtime;

CREATE FUNCTION public.validate_ipo_edge_final(b jsonb, closing date)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE stamp timestamptz:=clock_timestamp(); o jsonb; ref jsonb; field text; v numeric; groups int; official boolean:=false;
BEGIN
  IF (stamp AT TIME ZONE 'Asia/Kolkata')::date<>closing OR (stamp AT TIME ZONE 'Asia/Kolkata')::time<time '19:00'
    THEN RAISE EXCEPTION 'OUTSIDE_T2_WINDOW'; END IF;
  IF b->>'subscription_is_final' IS DISTINCT FROM 'true' OR jsonb_typeof(b->'final_subscriptions') IS DISTINCT FROM 'array'
    OR jsonb_array_length(b->'final_subscriptions')=0 THEN RAISE EXCEPTION 'FINAL_SUBSCRIPTION_NOT_VERIFIED'; END IF;
  FOR o IN SELECT * FROM jsonb_array_elements(b->'final_subscriptions') LOOP
    IF o->>'verified' IS DISTINCT FROM 'true' OR o->>'is_final' IS DISTINCT FROM 'true' OR coalesce(o->>'source_url','') NOT LIKE 'https://%'
       OR o->>'retrieved_at' IS NULL OR o->>'observed_at' IS NULL OR coalesce(o->>'basis','')=''
       OR (o->>'retrieved_at')::timestamptz>stamp OR (o->>'observed_at')::timestamptz>stamp
       OR ((o->>'observed_at')::timestamptz AT TIME ZONE 'Asia/Kolkata')::date<>closing THEN RAISE EXCEPTION 'INVALID_FINAL_EVIDENCE'; END IF;
    FOREACH field IN ARRAY ARRAY['total','qib','nii','retail'] LOOP
      IF jsonb_typeof(o->field) IS DISTINCT FROM 'number' THEN RAISE EXCEPTION 'MISSING_FINAL_FIELD:%',field; END IF;
      v:=(o->>field)::numeric;
      IF v<0 OR v::text IN ('NaN','Infinity','-Infinity') THEN RAISE EXCEPTION 'INVALID_FINAL_FIELD'; END IF;
      IF ref IS NOT NULL AND (abs(v-(ref->>field)::numeric)>.02 OR o->>'basis' IS DISTINCT FROM ref->>'basis') THEN RAISE EXCEPTION 'CONFLICTING_FINAL_SUBSCRIPTIONS'; END IF;
    END LOOP;
    ref:=o;
    official:=official OR (o->>'source_url' ~ '^https://([a-zA-Z0-9-]+\.)*(nseindia\.com|bseindia\.com|bsesme\.com|sebi\.gov\.in)(/|$)');
  END LOOP;
  SELECT count(DISTINCT o->>'provenance_group') INTO groups FROM jsonb_array_elements(b->'final_subscriptions') o
    WHERE length(trim(o->>'provenance_group'))>0 AND length(trim(o->>'independence_basis'))>0;
  IF NOT official AND groups<2 THEN RAISE EXCEPTION 'FINAL_CORROBORATION_REQUIRED'; END IF;
END $$;
REVOKE ALL ON FUNCTION public.validate_ipo_edge_final(jsonb,date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.validate_ipo_edge_final(jsonb,date) TO ipo_edge_runtime;
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
  PERFORM public.validate_ipo_edge_recovery(p_bundle);
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
  IF cp_type='T2_FINAL_DAY' THEN PERFORM public.validate_ipo_edge_final(p_bundle,ipo.issue_close_date); END IF;
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

CREATE FUNCTION public.finalize_ipo_edge_cycle(p_run bigint, audit jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE r public.run_log%ROWTYPE; seg text; groups int; valid boolean:=true; history_now jsonb; verdict text; row jsonb;
  obs jsonb; check_item jsonb; critical_missing boolean; day text:=(clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date::text;
BEGIN
  PERFORM pg_advisory_xact_lock(741103);
  SELECT * INTO STRICT r FROM public.run_log WHERE run_id=p_run FOR UPDATE;
  IF r.framework_version<>'1.1' OR r.status<>'STARTED' THEN RAISE EXCEPTION 'Cycle must be an active V1.1 run'; END IF;
  SELECT jsonb_build_object('count',count(*),'fingerprint',md5(string_agg(to_jsonb(c)::text,E'\n' ORDER BY checkpoint_id))) INTO history_now
    FROM public.checkpoints c WHERE framework_version='1.0';
  IF history_now IS DISTINCT FROM audit->'history_before' THEN RAISE EXCEPTION 'Historical integrity mismatch'; END IF;
  IF jsonb_typeof(audit->'observations') IS DISTINCT FROM 'array' OR jsonb_typeof(audit->'checks') IS DISTINCT FROM 'array'
    OR jsonb_typeof(audit->'conflicts') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'Cycle audit contract missing'; END IF;
  IF jsonb_array_length(audit->'conflicts')>0 THEN valid:=false; END IF;
  FOREACH seg IN ARRAY ARRAY['BSE','NSE','SEBI'] LOOP
    IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(coalesce(audit->'attempts','[]'::jsonb)) a WHERE a->>'provenance_group'=seg
      AND a->>'retrieved_at' IS NOT NULL AND (a->>'retrieved_at')::timestamptz<=clock_timestamp()) THEN valid:=false; END IF;
  END LOOP;
  FOR check_item IN SELECT * FROM jsonb_array_elements(audit->'checks') LOOP
    IF check_item->>'checks_run' IS DISTINCT FROM 'true' OR jsonb_typeof(check_item->'bundle'->'evidence') IS DISTINCT FROM 'array'
      THEN valid:=false; CONTINUE; END IF;
    BEGIN
      PERFORM public.validate_ipo_edge_recovery(check_item->'bundle');
      SELECT count(DISTINCT e->>'block') INTO groups FROM jsonb_array_elements(check_item->'bundle'->'evidence') e
        WHERE e->>'block' IN ('R1','R2','R3','R4','R5','R6','R7','R8') AND e->>'source_url' LIKE 'https://%'
        AND (e->>'retrieved_at')::timestamptz<=clock_timestamp();
      IF groups<>8 THEN valid:=false; END IF;
      SELECT count(DISTINCT e->>'block')<5 INTO critical_missing FROM jsonb_array_elements(check_item->'bundle'->'evidence') e
        WHERE e->>'block' IN ('R2','R3','R4','R6','R7') AND e->>'verified'='true';
      IF critical_missing AND check_item->>'disposition' IS DISTINCT FROM 'CRITICAL_EVIDENCE_NV' THEN valid:=false; END IF;
    EXCEPTION WHEN others THEN valid:=false;
    END;
  END LOOP;
  FOREACH seg IN ARRAY ARRAY['MAINBOARD','SME'] LOOP
    SELECT count(DISTINCT o->>'provenance_group') INTO groups FROM jsonb_array_elements(audit->'observations') o
      WHERE o->>'ok'='true' AND o->>'enumerated'='true' AND o->>'pagination_complete'='true'
      AND o->'segments_searched' ? seg AND length(trim(o->>'independence_basis'))>0 AND length(trim(o->>'provenance_group'))>0
      AND o->>'source_url' LIKE 'https://%' AND (o->>'retrieved_at')::timestamptz<=clock_timestamp()
      AND ((o->>'retrieved_at')::timestamptz AT TIME ZONE 'Asia/Kolkata')::date::text=day
      AND o->>'window_start'<=day AND o->>'window_end'>=day
      AND (EXISTS(SELECT 1 FROM jsonb_array_elements(o->'rows') x WHERE x->>'segment'=seg) OR o->'verified_empty'->>seg='true');
    IF groups<2 THEN valid:=false; END IF;
  END LOOP;
  -- Every discovered active issue needs an explicit disposition; no omitted-IPO success.
  FOR obs IN SELECT * FROM jsonb_array_elements(audit->'observations') LOOP
    FOR row IN SELECT * FROM jsonb_array_elements(coalesce(obs->'rows','[]'::jsonb)) LOOP
      IF row->>'issue_close_date'>=day AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(audit->'checks') c
        WHERE c->>'company_name'=row->>'company_name' AND c->>'checks_run'='true' AND c->>'recovery_complete'='true'
        AND c->>'disposition' IN ('VERIFIED','CRITICAL_EVIDENCE_NV')) THEN valid:=false; END IF;
      -- Calendar omission or conflicting dates between complete scans blocks completion.
      SELECT count(DISTINCT o->>'provenance_group') INTO groups FROM jsonb_array_elements(audit->'observations') o
        CROSS JOIN LATERAL jsonb_array_elements(coalesce(o->'rows','[]'::jsonb)) x
        WHERE o->>'ok'='true' AND o->>'enumerated'='true' AND o->>'pagination_complete'='true'
        AND length(trim(o->>'independence_basis'))>0 AND length(trim(o->>'provenance_group'))>0
        AND ((o->>'retrieved_at')::timestamptz AT TIME ZONE 'Asia/Kolkata')::date::text=day
        AND (o->>'retrieved_at')::timestamptz<=clock_timestamp()
        AND x->>'company_name'=row->>'company_name' AND x->>'segment'=row->>'segment'
        AND x->>'issue_open_date'=row->>'issue_open_date' AND x->>'issue_close_date'=row->>'issue_close_date';
      IF groups<2 THEN valid:=false; END IF;
      IF EXISTS(SELECT 1 FROM jsonb_array_elements(audit->'observations') o CROSS JOIN LATERAL jsonb_array_elements(coalesce(o->'rows','[]'::jsonb)) x
        WHERE x->>'company_name'=row->>'company_name' AND (x->>'segment' IS DISTINCT FROM row->>'segment'
          OR x->>'issue_close_date' IS DISTINCT FROM row->>'issue_close_date')) THEN valid:=false; END IF;
    END LOOP;
  END LOOP;
  IF EXISTS(SELECT 1 FROM public.ipos i WHERE i.issue_open_date<=day::date AND i.issue_close_date>=day::date
    AND i.status NOT IN ('WITHDRAWN','CANCELLED') AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(audit->'checks') c
      WHERE c->>'company_name'=i.company_name AND c->>'checks_run'='true' AND c->>'recovery_complete'='true')) THEN valid:=false; END IF;
  verdict:=CASE WHEN valid THEN 'COMPLETED' ELSE 'PARTIAL' END;
  INSERT INTO public.runtime_receipts(event_key,kind,run_id,payload) VALUES('cycle-final:'||p_run,'VALIDATION',p_run,
    audit||jsonb_build_object('status',verdict,'history_after',history_now));
  UPDATE public.run_log SET completed_at=clock_timestamp(),status=verdict,errors=CASE WHEN valid THEN '[]'::jsonb ELSE '["COVERAGE_OR_EVIDENCE_INCOMPLETE"]'::jsonb END WHERE run_id=p_run;
  RETURN jsonb_build_object('run_id',p_run,'status',verdict,'source_health',audit->>'source_health','history',history_now);
END $$;
REVOKE ALL ON FUNCTION public.finalize_ipo_edge_cycle(bigint,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.finalize_ipo_edge_cycle(bigint,jsonb) TO ipo_edge_runtime;
