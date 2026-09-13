CREATE FUNCTION public.refresh_ipo_edge_metrics()
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE runid bigint; result jsonb;
BEGIN
  PERFORM pg_advisory_xact_lock(741103);
  INSERT INTO public.run_log(run_type,framework_version) VALUES('INTEGRITY_AUDIT','1.1') RETURNING run_id INTO runid;
  WITH completed AS (
    SELECT c.*,o.listing_gain_percent,
      EXISTS(SELECT 1 FROM public.checkpoints p WHERE p.ipo_id=c.ipo_id AND p.checkpoint_time<c.checkpoint_time AND p.grade NOT IN ('A+','A++')) AS upgraded
    FROM public.listing_outcomes o JOIN LATERAL(SELECT * FROM public.checkpoints x WHERE x.ipo_id=o.ipo_id AND x.checkpoint_type='T2_FINAL_DAY'
      AND (x.checkpoint_time AT TIME ZONE 'Asia/Kolkata')::date<o.listing_date ORDER BY checkpoint_time DESC,checkpoint_id DESC LIMIT 1)c ON true
  ), totals AS (
    SELECT framework_version,count(*) n,count(*) FILTER(WHERE grade IN ('A+','A++')) rec,
      count(*) FILTER(WHERE grade IN ('A+','A++') AND listing_gain_percent>=0) pos,
      count(*) FILTER(WHERE grade IN ('A+','A++') AND listing_gain_percent>=20) strong,
      count(*) FILTER(WHERE grade='A++') app,count(*) FILTER(WHERE grade='A++' AND listing_gain_percent>=20) app_hit,
      count(*) FILTER(WHERE grade='A+') ap,count(*) FILTER(WHERE grade='A+' AND listing_gain_percent>=20) ap_hit,
      count(*) FILTER(WHERE listing_gain_percent>=20) winners,
      count(*) FILTER(WHERE grade NOT IN ('A+','A++') AND listing_gain_percent>=20) misses,
      count(*) FILTER(WHERE grade IN ('A+','A++') AND listing_gain_percent<0) fp,
      count(*) FILTER(WHERE grade NOT IN ('A+','A++') AND listing_gain_percent<20) correct,
      count(*) FILTER(WHERE upgraded AND grade IN ('A+','A++')) upgrades,
      count(*) FILTER(WHERE upgraded AND grade IN ('A+','A++') AND listing_gain_percent>=20) upgrade_hits,
      avg(listing_gain_percent) FILTER(WHERE grade IN ('A+','A++')) avg_gain,
      avg(base_gain_estimate) FILTER(WHERE grade IN ('A+','A++')) avg_est,
      avg(abs(listing_gain_percent-base_gain_estimate)) FILTER(WHERE grade IN ('A+','A++')) error
    FROM completed GROUP BY framework_version
  ) INSERT INTO public.efficacy_snapshots(as_of_date,framework_version,universe_count,recommendation_count,
    positive_hit_rate,twenty_percent_hit_rate,a_plus_plus_hit_rate,a_plus_hit_rate,opportunity_capture_rate,miss_rate,false_positive_rate,correct_avoidance_rate,
    avg_recommended_gain,avg_estimated_gain,forecast_error,upgrade_hit_rate)
  SELECT (clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date,framework_version,n,rec,pos::numeric/nullif(rec,0),strong::numeric/nullif(rec,0),
    app_hit::numeric/nullif(app,0),ap_hit::numeric/nullif(ap,0),strong::numeric/nullif(winners,0),misses::numeric/nullif(winners,0),fp::numeric/nullif(rec,0),
    correct::numeric/nullif(n-rec,0),avg_gain,avg_est,error,upgrade_hits::numeric/nullif(upgrades,0) FROM totals
  ON CONFLICT(as_of_date,framework_version) DO UPDATE SET universe_count=EXCLUDED.universe_count,recommendation_count=EXCLUDED.recommendation_count,
    positive_hit_rate=EXCLUDED.positive_hit_rate,twenty_percent_hit_rate=EXCLUDED.twenty_percent_hit_rate,a_plus_plus_hit_rate=EXCLUDED.a_plus_plus_hit_rate,
    a_plus_hit_rate=EXCLUDED.a_plus_hit_rate,opportunity_capture_rate=EXCLUDED.opportunity_capture_rate,miss_rate=EXCLUDED.miss_rate,
    false_positive_rate=EXCLUDED.false_positive_rate,correct_avoidance_rate=EXCLUDED.correct_avoidance_rate,avg_recommended_gain=EXCLUDED.avg_recommended_gain,
    avg_estimated_gain=EXCLUDED.avg_estimated_gain,forecast_error=EXCLUDED.forecast_error,upgrade_hit_rate=EXCLUDED.upgrade_hit_rate;
  SELECT jsonb_build_object('v1_count',count(*),'v1_fingerprint',md5(string_agg(to_jsonb(c)::text,E'\n' ORDER BY checkpoint_id))) INTO result
    FROM public.checkpoints c WHERE framework_version='1.0';
  INSERT INTO public.runtime_receipts(event_key,kind,run_id,payload) VALUES('integrity:'||runid,'INTEGRITY',runid,result);
  UPDATE public.run_log SET status='COMPLETED',completed_at=clock_timestamp() WHERE run_id=runid;
  RETURN result || jsonb_build_object('run_id',runid,'status','COMPLETED');
END;
$$;
REVOKE ALL ON FUNCTION public.refresh_ipo_edge_metrics() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.refresh_ipo_edge_metrics() TO ipo_edge_runtime;
