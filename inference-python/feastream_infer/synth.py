"""Synthetic labelled feature rows for training and testing the fraud model.

The generator encodes the domain intuition the real feature store would surface:
fraud looks like a burst of high-value, cross-border charges (high
``velocity_1m``, large ``amount_zscore``, multiple ``distinct_countries_5m``),
while legitimate activity is a calm trickle of small same-country purchases.
"""

from __future__ import annotations

import random
from typing import List, Tuple

from .model import FEATURE_ORDER


def _normal_row(rng: random.Random) -> List[float]:
    count = rng.randint(1, 8)
    amount = round(rng.uniform(15, 95), 2)
    mean = round(rng.uniform(25, 80), 2)
    std = round(rng.uniform(3, 25), 2)
    z = (amount - mean) / std if std > 0 else 0.0
    row = {
        "count_5m": count,
        "sum_5m": round(mean * count, 2),
        "mean_5m": mean,
        "std_5m": std,
        "velocity_1m": rng.randint(1, 2),
        "amount": amount,
        "amount_zscore": round(z, 2),
        "distinct_merchants_5m": rng.randint(1, 4),
        "distinct_countries_5m": 1,
    }
    return [float(row[k]) for k in FEATURE_ORDER]


def _fraud_row(rng: random.Random) -> List[float]:
    count = rng.randint(6, 16)
    amount = round(rng.uniform(800, 1700), 2)
    mean = round(rng.uniform(40, 120), 2)
    std = round(rng.uniform(20, 60), 2)
    z = (amount - mean) / std if std > 0 else 0.0
    row = {
        "count_5m": count,
        "sum_5m": round(mean * count + amount, 2),
        "mean_5m": mean,
        "std_5m": std,
        "velocity_1m": rng.randint(5, 12),
        "amount": amount,
        "amount_zscore": round(z, 2),
        "distinct_merchants_5m": rng.randint(3, 7),
        "distinct_countries_5m": rng.randint(2, 3),
    }
    return [float(row[k]) for k in FEATURE_ORDER]


def make_dataset(n: int = 1500, fraud_rate: float = 0.25, seed: int = 7
                 ) -> Tuple[List[List[float]], List[int]]:
    rng = random.Random(seed)
    X: List[List[float]] = []
    y: List[int] = []
    for _ in range(n):
        if rng.random() < fraud_rate:
            X.append(_fraud_row(rng))
            y.append(1)
        else:
            X.append(_normal_row(rng))
            y.append(0)
    return X, y
