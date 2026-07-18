from feastream_infer.gbdt import GBDT, sigmoid


def test_sigmoid_stable_extremes():
    assert 0.0 < sigmoid(-1000) < 1e-6
    assert 1.0 - 1e-6 < sigmoid(1000) <= 1.0
    assert abs(sigmoid(0.0) - 0.5) < 1e-9


def test_learns_axis_aligned_separation():
    # y depends only on feature 0 crossing 5.0
    X = [[float(i), float(i % 3)] for i in range(20)]
    y = [1 if row[0] > 5.0 else 0 for row in X]
    g = GBDT(n_estimators=40, max_depth=2, learning_rate=0.3).fit(X, y)
    for row, label in zip(X, y):
        p = g.predict_proba(row)
        assert (p > 0.5) == bool(label), f"row={row} p={p}"


def test_feature_importance_finds_signal():
    X = [[float(i), 0.0, float(i % 2)] for i in range(30)]
    y = [1 if row[0] > 15 else 0 for row in X]
    g = GBDT(n_estimators=30, max_depth=2).fit(X, y)
    imp = g.feature_importances()
    # feature 0 must carry the most gain
    assert max(imp, key=imp.get) == 0
