from ipo_edge.scoring import grade_from_score


def test_grade_thresholds():
    assert grade_from_score(95)[0] == "A++"
    assert grade_from_score(90)[0] == "A+"
    assert grade_from_score(85)[0] == "A"
    assert grade_from_score(84.99)[0] == "REJECT"
