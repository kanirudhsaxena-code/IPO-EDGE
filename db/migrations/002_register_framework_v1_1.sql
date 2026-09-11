INSERT INTO framework_versions (
  version,
  status,
  effective_at,
  scoring_config,
  rules_config,
  source_spec_document_url
)
VALUES (
  '1.1',
  'FROZEN',
  TIMESTAMPTZ '2026-09-11 13:40:00+00',
  '{"business_quality":15,"financial_quality":15,"valuation":20,"institutional_conviction":20,"market_demand":10,"analyst_consensus":10,"sector_ipo_environment":5,"gmp_confirmation":5}'::jsonb,
  '{"grade_A_plus_plus_min":95,"grade_A_plus_min":90,"grade_A_min":85,"missed_opportunity_threshold_pct":20,"critical_missing_evidence_blocks_high_conviction":true,"actionable_grades":["A++","A+"],"canonical_efficacy_checkpoint":"T2_FINAL_DAY","base_version":"1.0","institutional_demand_lane":{"name":"institutional_demand_lane","requirements":{"institutional_conviction_min":0.85,"market_demand_min":0.80,"all_critical_evidence_verified":true,"hard_blocker":false},"effect":"ACTIONABLE_CANDIDATE","historical_validation":{"development_precision":0.692,"development_recall":0.750,"validation_precision":0.750,"validation_recall":0.9231}},"evidence_recovery":{"mandatory_before_nv":true,"minimum_independent_source_attempts":2,"source_hierarchy_must_be_respected":true,"unresolved_critical_evidence_remains_nv":true,"never_impute_missing_critical_evidence":true},"rejected_changes":["lower_global_score_threshold","automatic_weight_reoptimization","relax_nv_gate"],"production_activation_approved":true}'::jsonb,
  'https://docs.google.com/document/d/17Znmj-rASDDuPbb9aRD9M6nZYlnDVVZfl7Qgg--eZjo/edit'
)
ON CONFLICT (version) DO NOTHING;
