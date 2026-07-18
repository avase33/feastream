"""Holdout evaluation: accuracy + ROC AUC, all from scratch."""

from __future__ import annotations

from typing import List

from .model import FraudModel
from .synth import make_dataset


def roc_auc(y_true: List[int], scores: List[float]) -> float:
    """Rank-based AUC (equivalent to the Mann-Whitney U statistic)."""
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # 1-based, averaged over ties
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    pos = sum(y_true)
    neg = len(y_true) - pos
    if pos == 0 or neg == 0:
        return 0.5
    sum_ranks_pos = sum(ranks[i] for i in range(len(y_true)) if y_true[i] == 1)
    return (sum_ranks_pos - pos * (pos + 1) / 2.0) / (pos * neg)


def run() -> dict:
    model = FraudModel.train(n=1500, seed=7)
    X, y = make_dataset(n=600, seed=999)  # disjoint holdout
    scores = [model.gbdt.predict_proba(x) for x in X]
    preds = [1 if s >= 0.5 else 0 for s in scores]
    acc = sum(1 for p, t in zip(preds, y) if p == t) / len(y)
    auc = roc_auc(y, scores)
    print(f"holdout: n={len(y)}  accuracy={acc:.3f}  auc={auc:.3f}")
    return {"accuracy": acc, "auc": auc}


if __name__ == "__main__":
    run()
