# feastream-infer

The inference node: a from-scratch, XGBoost-style gradient-boosted decision
tree fraud classifier plus a FastAPI `/score` endpoint. No numpy, no
scikit-learn, no lightgbm — the whole model is in `feastream_infer/gbdt.py`.

```bash
pip install -e ".[dev]"
python -m feastream_infer.cli demo     # train + score a calm vs a fraud vector
python -m feastream_infer.cli eval      # holdout accuracy + ROC AUC
feastream-infer serve                   # FastAPI on :8000
pytest -q
```

`/score` accepts a `{txn_id, user_id, ts, features}` body (features as in
`proto/protocol.md`) and returns a fraud probability, an allow/review/block
decision, and the model-derived top reasons.
