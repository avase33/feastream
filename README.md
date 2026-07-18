# feastream ⚡

**A real-time feature store for fraud detection.** Go absorbs the transaction
firehose, Rust keeps sliding-window features fresh in-memory at O(1) per event,
a from-scratch gradient-boosted model scores each charge, and a TypeScript
cockpit shows velocities, alerts, and end-to-end latency against a 10 ms budget.

Four languages, each on the layer it's built for, over one JSON protocol:

```
clients ──▶ Go gateway ──▶ Rust compute ──▶ Python inference ──▶ score
             │ (ingest+auth)  (sliding windows)  (GBDT fraud model)  │
             └──────────── Server-Sent Events ─────▶ TS cockpit ◀────┘
```

| Layer | Language | Owns |
| --- | --- | --- |
| **Gateway** | Go | Auth, ingest (HTTP + raw TCP), pub/sub ring + backpressure, SSE fan-out |
| **Compute** | Rust | O(1) rolling-window features in a thread-safe in-memory store |
| **Inference** | Python | XGBoost-style GBDT fraud classifier + FastAPI `/score` |
| **Cockpit** | TypeScript | Live velocities, fraud timeline, p50/p99 latency vs SLA |

Runs **offline** — no Redis, no numpy, no lightgbm. The Rust store is
self-contained, the fraud model is ~250 lines of pure-Python boosting, and the
gateway ships a built-in load generator that fires realistic fraud bursts.

## Quickstart — the model, offline

```bash
cd inference-python && pip install -e ".[dev]"
python -m feastream_infer.cli demo
```

```
feastream inference — training GBDT (from scratch)...
  60 trees, base_margin=-1.09x

 legit:  p=0.0xx  decision=allow   reasons=[]
 fraud:  p=0.9xx  decision=block   reasons=['velocity_1m=9', 'amount_zscore=4.2', ...]
```

Offline end-to-end check (trains, evaluates, scores — no services):

```bash
python scripts/verify.py     # RESULT: N passed, 0 failed
```

## Quickstart — the whole pipeline

```bash
docker compose up --build
# Cockpit:    http://localhost:3000   (watch fraud bursts light up the timeline)
# Gateway:    http://localhost:8080/healthz
# Compute:    http://localhost:8091/healthz
# Inference:  http://localhost:8000/healthz
```

The gateway runs with `FEASTREAM_SYNTH=1`, so the cockpit fills with live
traffic immediately. Post your own transaction:

```bash
curl -XPOST localhost:8080/ingest -H 'content-type: application/json' \
  -d '{"txn_id":"t1","user_id":"u_042","amount":1450,"merchant":"anon","country":"RU"}'
```

## The interesting engineering

- **Sliding-window compute (Rust)** — rolling `sum`/`sum of squares` updated
  incrementally on push and evict, so `count / mean / std / z-score` are O(1)
  per event over any window size. `compute-rust/src/window.rs`
- **From-scratch GBDT (Python)** — second-order (Newton) gradient boosting for
  logistic loss: XGBoost-style split gain `½(GL²/(HL+λ)+GR²/(HR+λ)−G²/(H+λ))−γ`
  and leaf weights `−G/(H+λ)`. Model-derived reason codes per decision.
  `inference-python/feastream_infer/gbdt.py`
- **Backpressure ring (Go)** — a non-blocking pub/sub buffer; a slow consumer
  is counted as `dropped`, never allowed to stall ingestion. `gateway-go/internal/ring`
- **Latency cockpit (TS)** — SSE stream, p99 sparkline drawn against the 10 ms
  SLA line, live fraud alert feed. `cockpit-ts/app/page.tsx`

## Testing

```bash
make test                         # rust + go + python
cd compute-rust    && cargo test
cd gateway-go      && go test ./...
cd inference-python && pytest -q
cd cockpit-ts      && npm run build
```

## Layout

```
proto/              shared JSON wire protocol
cockpit-ts/         Next.js operations cockpit (SSE, latency, alerts)
gateway-go/         Go ingestion proxy (auth, ring, pipeline, SSE)
compute-rust/       Rust sliding-window feature store (axum)
inference-python/   from-scratch GBDT fraud model + FastAPI
scripts/verify.py   offline end-to-end check
docs/ARCHITECTURE.md
```

## License

MIT © 2026 Akhil Vase
