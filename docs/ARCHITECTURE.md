# feastream architecture

A real-time feature store for fraud detection. Each language owns its domain;
one JSON contract (`proto/protocol.md`) connects them.

```
        clients / merchants
              │  HTTP /ingest  ·  raw TCP :9101
              ▼
┌──────────────────────────┐   POST /compute   ┌──────────────────────────┐
│ Gateway · Go             │ ────────────────▶ │ Compute · Rust           │
│ auth · pub/sub ring ·    │ ◀── FeatureVector │ sliding-window store      │
│ backpressure             │                   │ (O(1) rolling stats)      │
└───────┬──────────────────┘                   └──────────────────────────┘
        │ POST /score  { features }
        ▼
┌──────────────────────────┐
│ Inference · Python       │  from-scratch GBDT → fraud_probability + reasons
└───────┬──────────────────┘
        │ Server-Sent Events /stream  (ticks + alerts)
        ▼
┌──────────────────────────┐
│ Cockpit · TypeScript     │  ingest rate, p50/p99 vs 10 ms SLA, alert timeline
└──────────────────────────┘
```

## Why each language

| Layer | Language | Reason |
| --- | --- | --- |
| Gateway | **Go** | Cheap goroutines for thousands of concurrent ingest connections + fan-out. |
| Compute | **Rust** | Lock-tight, allocation-light rolling windows with no GC pauses on the hot path. |
| Inference | **Python** | Where models live — here an auditable from-scratch GBDT, no framework. |
| Cockpit | **TypeScript** | Live operational UI with canvas latency charts. |

## Flow

1. A transaction arrives at the Go gateway over HTTP `/ingest` or the raw TCP
   feed. The gateway authenticates it, publishes the raw event into an in-memory
   pub/sub **ring** (the offline stand-in for Redis Pub/Sub), and forwards it to
   the Rust compute service.
2. Rust updates that user's **sliding window**: rolling sum and sum-of-squares
   are adjusted incrementally on insert and on eviction of events older than
   300 s, so count / mean / std / z-score are O(1) per event. Distinct
   merchant/country counts use reference-counted maps. It returns a
   `FeatureVector`.
3. The gateway posts those features to the Python inference node, which scores
   them with the gradient-boosted model and returns a fraud probability, an
   allow/review/block decision, and model-derived reason codes.
4. The gateway records end-to-end latency, and for any non-`allow` decision
   pushes an alert over Server-Sent Events. Every second it also emits a metrics
   tick (ingest rate, p50/p99 latency, dropped count).
5. The TypeScript cockpit renders the live velocity, the p99 latency against the
   10 ms SLA line, and the fraud alert timeline.

## The model

Second-order gradient boosting for logistic loss. Each round computes the
gradient `g = p − y` and hessian `h = p(1−p)` per sample, grows a regression
tree that maximises the XGBoost split gain

    gain = ½ ( GL²/(HL+λ) + GR²/(HR+λ) − G²/(H+λ) ) − γ

and assigns each leaf the Newton-optimal weight `w = −G/(H+λ)`. Predictions
accumulate `learning_rate · w` across rounds. Reason codes come from attributing
each tree's output to the last feature that decided the sample's path — a cheap
model-derived stand-in for SHAP. See `inference-python/feastream_infer/gbdt.py`.

## Offline-first

- **Compute**: pure in-memory store, no Redis required.
- **Inference**: no numpy / lightgbm / sklearn — the whole model is Python.
- **Gateway**: a built-in synthetic load generator (`FEASTREAM_SYNTH=1`) fires
  realistic cross-border fraud bursts so the cockpit is alive on first boot.

`docker compose up` runs the full four-service pipeline; `make demo` scores
transactions with no services at all.
