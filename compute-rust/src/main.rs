//! HTTP front-end for the feature compute core (axum).
//!
//!   POST /compute            ingest one transaction, return its FeatureVector
//!   GET  /features/{user_id} last FeatureVector for a user
//!   GET  /healthz            liveness

use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use feastream_compute::{Aggregator, FeatureVector};
use serde::Deserialize;
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Deserialize)]
struct Transaction {
    #[allow(dead_code)]
    #[serde(default)]
    txn_id: String,
    user_id: String,
    amount: f64,
    #[serde(default)]
    merchant: String,
    #[serde(default)]
    country: String,
    #[serde(default)]
    ts: Option<f64>,
}

fn now_secs() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

async fn compute(
    State(agg): State<Arc<Aggregator>>,
    Json(t): Json<Transaction>,
) -> Json<FeatureVector> {
    let ts = t.ts.unwrap_or_else(now_secs);
    let merchant = if t.merchant.is_empty() {
        "unknown"
    } else {
        &t.merchant
    };
    let country = if t.country.is_empty() {
        "unknown"
    } else {
        &t.country
    };
    Json(agg.ingest(&t.user_id, ts, t.amount, merchant, country))
}

async fn features(
    State(agg): State<Arc<Aggregator>>,
    Path(user_id): Path<String>,
) -> Result<Json<FeatureVector>, StatusCode> {
    agg.latest_for(&user_id)
        .map(Json)
        .ok_or(StatusCode::NOT_FOUND)
}

async fn healthz(State(agg): State<Arc<Aggregator>>) -> Json<serde_json::Value> {
    Json(serde_json::json!({ "status": "ok", "users": agg.user_count() }))
}

#[tokio::main]
async fn main() {
    let agg = Arc::new(Aggregator::new());
    let app = Router::new()
        .route("/compute", post(compute))
        .route("/features/:user_id", get(features))
        .route("/healthz", get(healthz))
        .with_state(agg);

    let addr = std::env::var("FEASTREAM_COMPUTE_ADDR").unwrap_or_else(|_| "0.0.0.0:8091".into());
    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    println!("feastream-compute listening on {addr}");
    axum::serve(listener, app).await.unwrap();
}
