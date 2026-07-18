# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/); versioning: [SemVer](https://semver.org/).

## [0.1.0] - 2026-07-17

Initial release — a four-language real-time fraud feature store.

### Added
- **Rust compute**: thread-safe in-memory sliding-window feature store with
  incremental O(1) rolling sum / mean / std / z-score, reference-counted
  distinct merchant & country counts, and 1-minute velocity. axum `/compute`,
  `/features/:user`. Unit + integration tests incl. a 10k-event latency check.
- **Go gateway**: authenticated ingest over HTTP and a raw TCP feed, a
  non-blocking pub/sub ring with a dropped-message backpressure counter, the
  two-hop compute→inference pipeline, latency percentiles, an SSE cockpit
  stream, and a built-in fraud-burst load generator. Tests.
- **Python inference**: a from-scratch XGBoost-style gradient-boosted decision
  tree classifier (second-order logistic boosting, split gain, Newton leaf
  weights) with model-derived reason codes, holdout accuracy/AUC evaluation,
  synthetic data, FastAPI `/score`, CLI, and tests.
- **Next.js cockpit**: SSE-driven live velocities, a p99 latency sparkline
  against the 10 ms SLA line, and a fraud alert timeline.
- Shared JSON protocol, docker-compose, per-language Dockerfiles, multi-language
  CI, Makefile, offline verifier, MIT license.
