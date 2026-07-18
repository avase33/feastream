# feastream wire protocol

One JSON contract across all four languages. Every message is a single JSON
object on one line (newline-delimited JSON over TCP/WS, or a JSON body over
HTTP). Field names and types below are authoritative.

## 1. Transaction (client → Go gateway)

Raw event the gateway ingests. `POST /ingest` or newline-delimited over the
raw TCP feed (`:9101`).

```json
{
  "txn_id": "t_00013",
  "user_id": "u_042",
  "amount": 129.50,
  "currency": "USD",
  "merchant": "m_017",
  "country": "US",
  "ts": 1752710400.123
}
```

- `ts` is a Unix epoch **seconds** float. If omitted the gateway stamps arrival time.
- `amount` is always positive; refunds are modelled as a separate merchant class.

## 2. FeatureVector (Rust compute → feature store → Python)

Computed rolling-window features for a user at a point in time. Written to the
store keyed by `user_id`, and returned by the Rust `/features/{user_id}` route.

```json
{
  "user_id": "u_042",
  "ts": 1752710400.123,
  "features": {
    "count_5m": 7,
    "sum_5m": 903.5,
    "mean_5m": 129.07,
    "std_5m": 44.2,
    "velocity_1m": 3,
    "amount": 129.50,
    "amount_zscore": 0.71,
    "distinct_merchants_5m": 4,
    "distinct_countries_5m": 2
  }
}
```

Feature semantics (all windows are **sliding**, right-anchored at the event `ts`):

| feature | meaning |
| --- | --- |
| `count_5m` | number of transactions in the trailing 300 s |
| `sum_5m` / `mean_5m` / `std_5m` | rolling sum / mean / population std of `amount` |
| `velocity_1m` | transactions in the trailing 60 s (burst detector) |
| `amount` | the current transaction amount |
| `amount_zscore` | `(amount - mean_5m) / std_5m`, 0 when `std_5m == 0` |
| `distinct_merchants_5m` | unique merchants seen in the 5 m window |
| `distinct_countries_5m` | unique countries seen in the 5 m window |

## 3. Score (Python inference → Go → TS)

```json
{
  "txn_id": "t_00013",
  "user_id": "u_042",
  "ts": 1752710400.123,
  "fraud_probability": 0.87,
  "decision": "review",
  "top_reasons": ["velocity_1m=9", "amount_zscore=4.2", "distinct_countries_5m=3"],
  "latency_ms": 3.9
}
```

- `decision` ∈ `allow` (`p < 0.5`), `review` (`0.5 ≤ p < 0.85`), `block` (`p ≥ 0.85`).
- `top_reasons` are the features with the largest contribution to the score.

## 4. Dashboard frame (Go hub → TS over Server-Sent Events `/stream`)

The cockpit consumes a one-way server push, so the gateway uses SSE (an
`EventSource` on the browser) rather than a full WebSocket — no external Go
dependency, and it reconnects automatically.

```json
{
  "type": "tick",
  "ts": 1752710400.5,
  "ingest_rate": 1840,
  "p50_latency_ms": 2.1,
  "p99_latency_ms": 8.7,
  "alerts": [ { "...Score fields..." } ]
}
```

`type` is one of `tick` (periodic metrics) or `alert` (a single high-risk Score
pushed immediately).

## Ports

| service | port | protocol |
| --- | --- | --- |
| Go gateway | 8080 | HTTP `/ingest` `/healthz` + SSE `/stream` |
| Go raw feed | 9101 | TCP newline-delimited transactions |
| Rust compute | 8091 | HTTP `/compute` `/features/{user}` `/healthz` |
| Python inference | 8000 | HTTP `/score` `/healthz` |
| TS cockpit | 3000 | HTTP |
