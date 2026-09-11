from ipo_edge.component_rules import (
    score_business, score_financial, score_valuation, score_institutional,
    score_demand, score_analyst, score_environment, score_gmp,
)


def test_component_scores_are_bounded():
    values = [
        score_business(15, 250, 1.0),
        score_financial(30, 30, 0.2),
        score_valuation(15),
        score_institutional(100),
        score_demand(50, 50, 10),
        score_analyst(8, 10),
        score_environment(4, 16),
        score_gmp(30),
    ]
    assert all(v is not None and 0 <= v <= 1 for v in values)


def test_business_requires_two_metrics():
    assert score_business(company_age_years=10) is None


def test_business_rewards_scale_and_profitability_continuity():
    assert score_business(20, 400, 1.0) > score_business(3, 20, 0.5)


def test_financial_requires_two_metrics():
    assert score_financial(20, None, None) is None


def test_analyst_depth_does_not_override_consensus():
    assert score_analyst(0, 15) < score_analyst(10, 15)


def test_environment_rewards_positive_low_vol_regime():
    assert score_environment(6, 15) > score_environment(-8, 35)
