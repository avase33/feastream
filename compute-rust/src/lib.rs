//! feastream compute core: a thread-safe, in-memory feature store.
//!
//! `Aggregator` owns one [`SlidingWindow`] per user behind a single
//! `RwLock`. Reads of the latest feature vector take a shared lock; ingesting
//! a transaction takes the write lock only for the microseconds needed to push
//! and recompute. This is the "in-memory database" the architecture diagram
//! refers to — no external store required to run.

pub mod window;

use serde::Serialize;
use std::collections::HashMap;
use std::sync::RwLock;
use window::{Event, Features, SlidingWindow};

#[derive(Clone, Serialize)]
pub struct FeatureVector {
    pub user_id: String,
    pub ts: f64,
    pub features: Features,
}

#[derive(Default)]
pub struct Aggregator {
    windows: RwLock<HashMap<String, SlidingWindow>>,
    latest: RwLock<HashMap<String, FeatureVector>>,
}

impl Aggregator {
    pub fn new() -> Self {
        Aggregator {
            windows: RwLock::new(HashMap::new()),
            latest: RwLock::new(HashMap::new()),
        }
    }

    /// Ingest a transaction and return the freshly computed feature vector.
    pub fn ingest(
        &self,
        user_id: &str,
        ts: f64,
        amount: f64,
        merchant: &str,
        country: &str,
    ) -> FeatureVector {
        let features = {
            let mut map = self.windows.write().unwrap();
            let w = map.entry(user_id.to_string()).or_default();
            w.push(Event {
                ts,
                amount,
                merchant: merchant.to_string(),
                country: country.to_string(),
            })
        };
        let fv = FeatureVector {
            user_id: user_id.to_string(),
            ts,
            features,
        };
        self.latest
            .write()
            .unwrap()
            .insert(user_id.to_string(), fv.clone());
        fv
    }

    /// Return the last computed feature vector for a user, if any.
    pub fn latest_for(&self, user_id: &str) -> Option<FeatureVector> {
        self.latest.read().unwrap().get(user_id).cloned()
    }

    pub fn user_count(&self) -> usize {
        self.windows.read().unwrap().len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ingest_returns_features_and_caches_latest() {
        let agg = Aggregator::new();
        agg.ingest("u1", 0.0, 100.0, "m1", "US");
        let fv = agg.ingest("u1", 1.0, 300.0, "m2", "CA");
        assert_eq!(fv.features.count_5m, 2);
        assert_eq!(fv.features.sum_5m, 400.0);
        let cached = agg.latest_for("u1").unwrap();
        assert_eq!(cached.features.count_5m, 2);
        assert_eq!(agg.user_count(), 1);
    }

    #[test]
    fn users_are_isolated() {
        let agg = Aggregator::new();
        agg.ingest("a", 0.0, 100.0, "m", "US");
        agg.ingest("b", 0.0, 50.0, "m", "US");
        assert_eq!(agg.latest_for("a").unwrap().features.sum_5m, 100.0);
        assert_eq!(agg.latest_for("b").unwrap().features.sum_5m, 50.0);
        assert!(agg.latest_for("c").is_none());
    }
}
