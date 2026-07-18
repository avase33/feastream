"""Offline demo: train the model and score a calm vs. a fraud feature vector."""

from __future__ import annotations

from .model import FraudModel


def run() -> None:
    print("feastream inference — training GBDT (from scratch)...")
    model = FraudModel.train()
    print(f"  {len(model.gbdt.trees)} trees, base_margin={model.gbdt.base_margin:.3f}\n")

    calm = {
        "count_5m": 3,
        "sum_5m": 150.0,
        "mean_5m": 50.0,
        "std_5m": 10.0,
        "velocity_1m": 1,
        "amount": 42.0,
        "amount_zscore": -0.8,
        "distinct_merchants_5m": 2,
        "distinct_countries_5m": 1,
    }
    fraud = {
        "count_5m": 11,
        "sum_5m": 5400.0,
        "mean_5m": 90.0,
        "std_5m": 40.0,
        "velocity_1m": 9,
        "amount": 1450.0,
        "amount_zscore": 4.2,
        "distinct_merchants_5m": 5,
        "distinct_countries_5m": 3,
    }

    for label, feats in [("legit", calm), ("fraud", fraud)]:
        p, decision, reasons = model.score(feats)
        print(f"{label:>6}:  p={p:.3f}  decision={decision:<6}  reasons={reasons}")


if __name__ == "__main__":
    run()
