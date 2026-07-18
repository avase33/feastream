from feastream_infer.evaluate import roc_auc, run as eval_run
from feastream_infer.model import FraudModel

CALM = {
    "count_5m": 3, "sum_5m": 150.0, "mean_5m": 50.0, "std_5m": 10.0,
    "velocity_1m": 1, "amount": 42.0, "amount_zscore": -0.8,
    "distinct_merchants_5m": 2, "distinct_countries_5m": 1,
}
FRAUD = {
    "count_5m": 11, "sum_5m": 5400.0, "mean_5m": 90.0, "std_5m": 40.0,
    "velocity_1m": 9, "amount": 1450.0, "amount_zscore": 4.2,
    "distinct_merchants_5m": 5, "distinct_countries_5m": 3,
}

_MODEL = FraudModel.train(n=1200, seed=7)


def test_calm_is_allowed_fraud_is_flagged():
    p_calm, dec_calm, _ = _MODEL.score(CALM)
    p_fraud, dec_fraud, reasons = _MODEL.score(FRAUD)
    assert p_calm < 0.5, f"calm p={p_calm}"
    assert p_fraud > 0.5, f"fraud p={p_fraud}"
    assert dec_calm == "allow"
    assert dec_fraud in ("review", "block")
    assert reasons, "fraud score should surface reasons"


def test_roc_auc_ranking():
    # perfect ranking -> auc 1.0; reversed -> 0.0
    assert abs(roc_auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) - 1.0) < 1e-9
    assert abs(roc_auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) - 0.0) < 1e-9


def test_holdout_quality():
    metrics = eval_run()
    assert metrics["accuracy"] > 0.9
    assert metrics["auc"] > 0.95
