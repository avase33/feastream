"""FastAPI inference node.

Trains the from-scratch GBDT once at startup, then scores incoming feature
vectors. Kept dependency-light: only FastAPI/pydantic, no ML frameworks.
"""

from __future__ import annotations

import os
import time
from typing import Dict, List

from fastapi import FastAPI
from pydantic import BaseModel

from .model import FraudModel

app = FastAPI(title="feastream inference", version="0.1.0")
_model: FraudModel | None = None


def get_model() -> FraudModel:
    global _model
    if _model is None:
        n = int(os.getenv("FEASTREAM_TRAIN_N", "1500"))
        _model = FraudModel.train(n=n)
    return _model


class ScoreRequest(BaseModel):
    txn_id: str = ""
    user_id: str = ""
    ts: float = 0.0
    features: Dict[str, float] = {}


class ScoreResponse(BaseModel):
    txn_id: str
    user_id: str
    ts: float
    fraud_probability: float
    decision: str
    top_reasons: List[str]
    latency_ms: float


@app.on_event("startup")
def _warm() -> None:
    get_model()


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "trees": len(get_model().gbdt.trees)}


@app.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest) -> ScoreResponse:
    start = time.perf_counter()
    prob, decision, reasons = get_model().score(req.features)
    return ScoreResponse(
        txn_id=req.txn_id,
        user_id=req.user_id,
        ts=req.ts,
        fraud_probability=round(prob, 4),
        decision=decision,
        top_reasons=reasons,
        latency_ms=round((time.perf_counter() - start) * 1000.0, 3),
    )
