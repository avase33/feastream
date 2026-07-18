"""A gradient-boosted decision tree classifier, written from scratch.

This is an XGBoost-style second-order gradient boosting machine for binary
logistic loss — no numpy, no scikit-learn, no lightgbm. It exists so the whole
fraud model is auditable end to end.

Per boosting round on logistic loss with margin ``F``:

    p_i = sigmoid(F_i)
    g_i = p_i - y_i            # first-order gradient
    h_i = p_i * (1 - p_i)      # second-order (hessian)

Each regression tree is grown greedily, choosing the split that maximises the
XGBoost gain

    gain = 1/2 * ( GL^2/(HL+λ) + GR^2/(HR+λ) - G^2/(H+λ) ) - γ

and every leaf takes the Newton-optimal weight ``w = -G/(H+λ)``. Predictions
accumulate ``learning_rate * w`` across rounds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


@dataclass
class _Node:
    feature: int = -1
    threshold: float = 0.0
    left: Optional["_Node"] = None
    right: Optional["_Node"] = None
    value: float = 0.0
    is_leaf: bool = False


def _candidate_thresholds(values: List[float], max_bins: int) -> List[float]:
    """Quantile-ish candidate split points for one feature at a node."""
    uniq = sorted(set(values))
    if len(uniq) <= 1:
        return []
    if len(uniq) - 1 <= max_bins:
        return [(uniq[i] + uniq[i + 1]) / 2.0 for i in range(len(uniq) - 1)]
    out = []
    step = (len(uniq) - 1) / max_bins
    for b in range(1, max_bins + 1):
        i = min(len(uniq) - 1, int(b * step))
        out.append((uniq[i - 1] + uniq[i]) / 2.0)
    return sorted(set(out))


class _Tree:
    def __init__(self, max_depth: int, lam: float, gamma: float,
                 min_child_weight: float, max_bins: int):
        self.max_depth = max_depth
        self.lam = lam
        self.gamma = gamma
        self.min_child_weight = min_child_weight
        self.max_bins = max_bins
        self.root: Optional[_Node] = None
        # feature -> total gain, accumulated while building
        self.gain_by_feature: dict[int, float] = {}

    def _leaf_value(self, g_sum: float, h_sum: float) -> float:
        return -g_sum / (h_sum + self.lam)

    def fit(self, X, g, h, n_features: int):
        idx = list(range(len(X)))
        self.root = self._build(X, g, h, idx, 0, n_features)

    def _build(self, X, g, h, idx, depth, n_features) -> _Node:
        g_sum = sum(g[i] for i in idx)
        h_sum = sum(h[i] for i in idx)
        node = _Node(value=self._leaf_value(g_sum, h_sum), is_leaf=True)

        if depth >= self.max_depth or len(idx) < 2 or h_sum < self.min_child_weight:
            return node

        base = g_sum * g_sum / (h_sum + self.lam)
        best_gain = 0.0
        best_feat = -1
        best_thr = 0.0

        for f in range(n_features):
            vals = [X[i][f] for i in idx]
            for thr in _candidate_thresholds(vals, self.max_bins):
                gl = hl = 0.0
                for i in idx:
                    if X[i][f] <= thr:
                        gl += g[i]
                        hl += h[i]
                gr = g_sum - gl
                hr = h_sum - hl
                if hl < self.min_child_weight or hr < self.min_child_weight:
                    continue
                gain = 0.5 * (
                    gl * gl / (hl + self.lam)
                    + gr * gr / (hr + self.lam)
                    - base
                ) - self.gamma
                if gain > best_gain:
                    best_gain = gain
                    best_feat = f
                    best_thr = thr

        if best_feat < 0:
            return node

        left_idx = [i for i in idx if X[i][best_feat] <= best_thr]
        right_idx = [i for i in idx if X[i][best_feat] > best_thr]
        if not left_idx or not right_idx:
            return node

        self.gain_by_feature[best_feat] = self.gain_by_feature.get(best_feat, 0.0) + best_gain
        return _Node(
            feature=best_feat,
            threshold=best_thr,
            is_leaf=False,
            left=self._build(X, g, h, left_idx, depth + 1, n_features),
            right=self._build(X, g, h, right_idx, depth + 1, n_features),
        )

    def predict(self, x) -> float:
        node = self.root
        while node is not None and not node.is_leaf:
            node = node.left if x[node.feature] <= node.threshold else node.right
        return node.value if node else 0.0

    def deciding_feature(self, x) -> int:
        """The last feature tested on x's root-to-leaf path (-1 if a stump leaf)."""
        node = self.root
        last = -1
        while node is not None and not node.is_leaf:
            last = node.feature
            node = node.left if x[node.feature] <= node.threshold else node.right
        return last


@dataclass
class GBDT:
    n_estimators: int = 60
    learning_rate: float = 0.3
    max_depth: int = 3
    lam: float = 1.0
    gamma: float = 0.0
    min_child_weight: float = 1.0
    max_bins: int = 24
    base_margin: float = 0.0
    trees: List[_Tree] = field(default_factory=list)
    n_features: int = 0

    def fit(self, X: List[List[float]], y: List[int]) -> "GBDT":
        n = len(X)
        self.n_features = len(X[0]) if n else 0
        pos = sum(y) or 1
        rate = pos / max(n, 1)
        rate = min(max(rate, 1e-6), 1 - 1e-6)
        self.base_margin = math.log(rate / (1 - rate))
        self.trees = []

        f = [self.base_margin] * n
        for _ in range(self.n_estimators):
            g = [0.0] * n
            h = [0.0] * n
            for i in range(n):
                p = sigmoid(f[i])
                g[i] = p - y[i]
                h[i] = max(p * (1 - p), 1e-6)
            tree = _Tree(self.max_depth, self.lam, self.gamma,
                         self.min_child_weight, self.max_bins)
            tree.fit(X, g, h, self.n_features)
            for i in range(n):
                f[i] += self.learning_rate * tree.predict(X[i])
            self.trees.append(tree)
        return self

    def margin(self, x: List[float]) -> float:
        m = self.base_margin
        for t in self.trees:
            m += self.learning_rate * t.predict(x)
        return m

    def predict_proba(self, x: List[float]) -> float:
        return sigmoid(self.margin(x))

    def feature_importances(self) -> dict[int, float]:
        total: dict[int, float] = {}
        for t in self.trees:
            for f, gain in t.gain_by_feature.items():
                total[f] = total.get(f, 0.0) + gain
        return total

    def contributions(self, x: List[float]) -> dict[int, float]:
        """Per-feature signed contribution to x's margin.

        Attributes each tree's output to the last feature that decided x's path
        through it — a cheap, model-derived alternative to SHAP for surfacing
        *why* a transaction scored the way it did.
        """
        contrib: dict[int, float] = {}
        for t in self.trees:
            f = t.deciding_feature(x)
            if f < 0:
                continue
            contrib[f] = contrib.get(f, 0.0) + self.learning_rate * t.predict(x)
        return contrib
