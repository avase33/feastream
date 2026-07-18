//! Stateful sliding-window aggregator.
//!
//! Each `SlidingWindow` tracks one user's transaction history over a trailing
//! 5-minute horizon. Rolling `sum` and `sum of squares` are maintained
//! **incrementally** on every push/evict, so `count / mean / std` are O(1) per
//! event regardless of window size. Distinct-merchant and distinct-country
//! counts are kept with reference-counted hash maps (increment on insert,
//! decrement on evict, `distinct = map.len()`), also O(1) amortised.
//!
//! The only non-constant step is `velocity_1m`, which scans backwards from the
//! newest event until it passes the 60 s boundary — that touches at most the
//! events inside the 1-minute window, which is exactly the quantity reported.

use serde::Serialize;
use std::collections::{HashMap, VecDeque};

pub const WIN_5M: f64 = 300.0;
pub const WIN_1M: f64 = 60.0;

#[derive(Clone)]
pub struct Event {
    pub ts: f64,
    pub amount: f64,
    pub merchant: String,
    pub country: String,
}

/// The computed feature row for a single transaction. Field names match
/// `proto/protocol.md` exactly so this serialises straight onto the wire.
#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct Features {
    pub count_5m: u64,
    pub sum_5m: f64,
    pub mean_5m: f64,
    pub std_5m: f64,
    pub velocity_1m: u64,
    pub amount: f64,
    pub amount_zscore: f64,
    pub distinct_merchants_5m: u64,
    pub distinct_countries_5m: u64,
}

pub struct SlidingWindow {
    events: VecDeque<Event>,
    sum: f64,
    sumsq: f64,
    merchants: HashMap<String, u32>,
    countries: HashMap<String, u32>,
    win: f64,
    vel_win: f64,
}

impl Default for SlidingWindow {
    fn default() -> Self {
        Self::new()
    }
}

impl SlidingWindow {
    pub fn new() -> Self {
        SlidingWindow {
            events: VecDeque::new(),
            sum: 0.0,
            sumsq: 0.0,
            merchants: HashMap::new(),
            countries: HashMap::new(),
            win: WIN_5M,
            vel_win: WIN_1M,
        }
    }

    fn dec(map: &mut HashMap<String, u32>, key: &str) {
        if let Some(c) = map.get_mut(key) {
            *c -= 1;
            if *c == 0 {
                map.remove(key);
            }
        }
    }

    /// Drop everything strictly older than `win` seconds before `now`,
    /// updating the incremental accumulators as we go.
    fn evict(&mut self, now: f64) {
        while let Some(front) = self.events.front() {
            if now - front.ts > self.win {
                let e = self.events.pop_front().unwrap();
                self.sum -= e.amount;
                self.sumsq -= e.amount * e.amount;
                Self::dec(&mut self.merchants, &e.merchant);
                Self::dec(&mut self.countries, &e.country);
            } else {
                break;
            }
        }
    }

    /// Ingest one event and return the feature row computed at its timestamp.
    pub fn push(&mut self, e: Event) -> Features {
        let now = e.ts;
        let amount = e.amount;
        self.sum += e.amount;
        self.sumsq += e.amount * e.amount;
        *self.merchants.entry(e.merchant.clone()).or_insert(0) += 1;
        *self.countries.entry(e.country.clone()).or_insert(0) += 1;
        self.events.push_back(e);
        self.evict(now);
        self.compute(now, amount)
    }

    fn compute(&self, now: f64, amount: f64) -> Features {
        let n = self.events.len() as f64;
        let mean = if n > 0.0 { self.sum / n } else { 0.0 };
        // population variance, clamped to 0 to absorb float cancellation
        let var = if n > 0.0 {
            (self.sumsq / n - mean * mean).max(0.0)
        } else {
            0.0
        };
        let std = var.sqrt();
        let zscore = if std > 1e-9 { (amount - mean) / std } else { 0.0 };

        let mut velocity_1m = 0u64;
        for ev in self.events.iter().rev() {
            if now - ev.ts <= self.vel_win {
                velocity_1m += 1;
            } else {
                break;
            }
        }

        Features {
            count_5m: self.events.len() as u64,
            sum_5m: round2(self.sum),
            mean_5m: round2(mean),
            std_5m: round2(std),
            velocity_1m,
            amount: round2(amount),
            amount_zscore: round2(zscore),
            distinct_merchants_5m: self.merchants.len() as u64,
            distinct_countries_5m: self.countries.len() as u64,
        }
    }

    pub fn len(&self) -> usize {
        self.events.len()
    }

    pub fn is_empty(&self) -> bool {
        self.events.is_empty()
    }
}

fn round2(x: f64) -> f64 {
    (x * 100.0).round() / 100.0
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ev(ts: f64, amount: f64, m: &str, c: &str) -> Event {
        Event {
            ts,
            amount,
            merchant: m.to_string(),
            country: c.to_string(),
        }
    }

    #[test]
    fn counts_and_mean() {
        let mut w = SlidingWindow::new();
        w.push(ev(0.0, 100.0, "m1", "US"));
        w.push(ev(1.0, 200.0, "m2", "US"));
        let f = w.push(ev(2.0, 300.0, "m1", "CA"));
        assert_eq!(f.count_5m, 3);
        assert_eq!(f.sum_5m, 600.0);
        assert_eq!(f.mean_5m, 200.0);
        assert_eq!(f.distinct_merchants_5m, 2);
        assert_eq!(f.distinct_countries_5m, 2);
    }

    #[test]
    fn evicts_old_events() {
        let mut w = SlidingWindow::new();
        w.push(ev(0.0, 100.0, "m1", "US"));
        w.push(ev(10.0, 100.0, "m1", "US"));
        // 400 s later: both original events are outside the 5 m window
        let f = w.push(ev(400.0, 50.0, "m2", "GB"));
        assert_eq!(f.count_5m, 1);
        assert_eq!(f.sum_5m, 50.0);
        assert_eq!(f.distinct_merchants_5m, 1);
        assert_eq!(f.distinct_countries_5m, 1);
    }

    #[test]
    fn velocity_only_counts_last_minute() {
        let mut w = SlidingWindow::new();
        w.push(ev(0.0, 10.0, "m", "US"));
        w.push(ev(30.0, 10.0, "m", "US"));
        w.push(ev(50.0, 10.0, "m", "US"));
        // event at t=120: only t=120 itself is within 60 s (90,100 gap)
        let f = w.push(ev(120.0, 10.0, "m", "US"));
        assert_eq!(f.velocity_1m, 1);
        assert_eq!(f.count_5m, 4); // all still within 300 s
    }

    #[test]
    fn zscore_zero_when_no_variance() {
        let mut w = SlidingWindow::new();
        w.push(ev(0.0, 100.0, "m", "US"));
        let f = w.push(ev(1.0, 100.0, "m", "US"));
        assert_eq!(f.std_5m, 0.0);
        assert_eq!(f.amount_zscore, 0.0);
    }

    #[test]
    fn zscore_flags_outlier() {
        let mut w = SlidingWindow::new();
        for i in 0..9 {
            w.push(ev(i as f64, 100.0, "m", "US"));
        }
        let f = w.push(ev(9.0, 1000.0, "m", "US"));
        // a 1000 amount against a cluster of 100s must be a large positive z
        assert!(f.amount_zscore > 2.0, "z={}", f.amount_zscore);
    }
}
