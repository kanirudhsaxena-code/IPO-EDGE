-- Learning evaluation may progress autonomously; adopted/rejected history stays protected.
CREATE FUNCTION public.record_ipo_edge_learning_evaluation(p_id bigint, p_evaluation jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE status_now text; proposed text:=p_evaluation->>'status'; runid bigint;
BEGIN
  PERFORM pg_advisory_xact_lock(741103);
  SELECT status INTO STRICT status_now FROM public.learnings WHERE learning_id=p_id AND adopted_framework_version IS NULL;
  IF status_now IN ('ADOPTED','REJECTED') THEN RAISE EXCEPTION 'Historical learning state is protected'; END IF;
  IF proposed NOT IN ('TESTING','VALIDATED','REJECTED') OR proposed IS NULL THEN RAISE EXCEPTION 'Adoption is not an autonomous operation'; END IF;
  IF p_evaluation->>'development_result' IS NULL OR p_evaluation->>'validation_result' IS NULL
     OR p_evaluation->>'evidence_query' IS NULL OR p_evaluation->>'sample_adequacy' IS NULL THEN RAISE EXCEPTION 'Auditable evaluation results required'; END IF;
  IF proposed='VALIDATED' AND (p_evaluation->>'unseen_validation') IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'Unseen validation required'; END IF;
  INSERT INTO public.run_log(run_type,framework_version) VALUES('LEARNING_EVALUATION','1.1') RETURNING run_id INTO runid;
  INSERT INTO public.runtime_receipts(event_key,kind,run_id,payload) VALUES('learning-evaluation:'||runid,'VALIDATION',runid,p_evaluation||jsonb_build_object('learning_id',p_id));
  UPDATE public.learnings SET status=proposed,development_result=p_evaluation->>'development_result',validation_result=p_evaluation->>'validation_result',updated_at=clock_timestamp()
    WHERE learning_id=p_id AND adopted_framework_version IS NULL AND status IN ('TESTING','VALIDATED');
  UPDATE public.run_log SET status='COMPLETED',completed_at=clock_timestamp() WHERE run_id=runid;
  RETURN jsonb_build_object('status',proposed,'learning_id',p_id,'run_id',runid,'production_changed',false);
END;
$$;
REVOKE ALL ON FUNCTION public.record_ipo_edge_learning_evaluation(bigint,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.record_ipo_edge_learning_evaluation(bigint,jsonb) TO ipo_edge_runtime;
