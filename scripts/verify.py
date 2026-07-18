#!/usr/bin/env python3
"""Offline end-to-end verifier for feastream.

Trains the from-scratch GBDT, checks holdout quality, and exercises the scoring
path on a calm and a fraud feature vector — all with zero services running and
zero external ML dependencies. Exits non-zero on any failure.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "inference-python"))

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")


def main() -> int:
    from feastream_infer.evaluate import run as eval_run
    from feastream_infer.model import FraudModel

    print("feastream offline verify")
    model = FraudModel.train(n=1200, seed=7)
    check("model trained trees>0", len(model.gbdt.trees) > 0)

    calm = {
        "count_5m": 3, "sum_5m": 150.0, "mean_5m": 50.0, "std_5m": 10.0,
        "velocity_1m": 1, "amount": 42.0, "amount_zscore": -0.8,
        "distinct_merchants_5m": 2, "distinct_countries_5m": 1,
    }
    fraud = {
        "count_5m": 11, "sum_5m": 5400.0, "mean_5m": 90.0, "std_5m": 40.0,
        "velocity_1m": 9, "amount": 1450.0, "amount_zscore": 4.2,
        "distinct_merchants_5m": 5, "distinct_countries_5m": 3,
    }
    p_calm, dec_calm, _ = model.score(calm)
    p_fraud, dec_fraud, reasons = model.score(fraud)
    check("calm scored allow", dec_calm == "allow" and p_calm < 0.5)
    check("fraud flagged", dec_fraud in ("review", "block") and p_fraud > 0.5)
    check("fraud has reasons", len(reasons) > 0)

    metrics = eval_run()
    check("holdout accuracy > 0.9", metrics["accuracy"] > 0.9)
    check("holdout auc > 0.95", metrics["auc"] > 0.95)

    print(f"\nRESULT: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
