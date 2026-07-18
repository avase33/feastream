"""FraudModel: trains the GBDT on synthetic features and scores live ones."""

from __future__ import annotations

from typing import Dict, List, Tuple

from .gbdt import GBDT

# Canonical feature ordering. Must match proto/protocol.md and the Rust output.
FEATURE_ORDER: List[str] = [
    "count_5m",
    "sum_5m",
    "mean_5m",
    "std_5m",
    "velocity_1m",
    "amount",
    "amount_zscore",
    "distinct_merchants_5m",
    "distinct_countries_5m",
]

# Human-readable labels for the reason strings.
_PRETTY = {
    "velocity_1m": "velocity_1m",
    "amount_zscore": "amount_zscore",
    "distinct_countries_5m": "distinct_countries_5m",
    "distinct_merchants_5m": "distinct_merchants_5m",
    "amount": "amount",
    "count_5m": "count_5m",
    "sum_5m": "sum_5m",
    "mean_5m": "mean_5m",
    "std_5m": "std_5m",
}

REVIEW_THRESHOLD = 0.5
BLOCK_THRESHOLD = 0.85


def vectorize(features: Dict[str, float]) -> List[float]:
    return [float(features.get(k, 0.0)) for k in FEATURE_ORDER]


class FraudModel:
    def __init__(self, gbdt: GBDT | None = None):
        self.gbdt = gbdt or GBDT()

    @classmethod
    def train(cls, n: int = 1500, seed: int = 7, **gbdt_kwargs) -> "FraudModel":
        # imported here to avoid a circular import at module load time
        from .synth import make_dataset

        X, y = make_dataset(n=n, seed=seed)
        model = cls(GBDT(**gbdt_kwargs))
        model.gbdt.fit(X, y)
        return model

    def decision(self, prob: float) -> str:
        if prob >= BLOCK_THRESHOLD:
            return "block"
        if prob >= REVIEW_THRESHOLD:
            return "review"
        return "allow"

    def top_reasons(self, features: Dict[str, float], k: int = 3) -> List[str]:
        x = vectorize(features)
        contrib = self.gbdt.contributions(x)
        # only reasons that push *towards* fraud (positive margin contribution)
        ranked = sorted(
            ((f, c) for f, c in contrib.items() if c > 0),
            key=lambda kv: kv[1],
            reverse=True,
        )
        reasons = []
        for f, _ in ranked[:k]:
            name = FEATURE_ORDER[f]
            val = features.get(name, 0.0)
            val_str = f"{val:g}" if isinstance(val, (int, float)) else str(val)
            reasons.append(f"{_PRETTY.get(name, name)}={val_str}")
        return reasons

    def score(self, features: Dict[str, float]) -> Tuple[float, str, List[str]]:
        prob = self.gbdt.predict_proba(vectorize(features))
        return prob, self.decision(prob), self.top_reasons(features)
