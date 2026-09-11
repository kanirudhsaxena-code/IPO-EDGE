from ipo_edge.component_rules import (
    score_financial, score_valuation, score_institutional,
    score_demand, score_analyst, score_gmp,
)


def test_component_scores_are_bounded():
    values = [
        score_financial(30, 30, 0.2),
        score_valuation(15),
        score_institutional(100),
        score_demand(50, 50, 10),
        score_analyst(8, 10),
        score_gmp(30),
    ]
    assert all(v is not None and 0 <= v <= 1 for v in values)


def test_financial_requires_two_metrics():
    assert score_financial(20, None, None) is None


def test_analyst_depth_does_not_override_consensus():
    assert score_analyst(0, 15) < score_analyst(10, 15)
