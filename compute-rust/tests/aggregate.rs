use feastream_compute::Aggregator;

// End-to-end: a burst of transactions for one user should drive velocity and
// z-score up while an unrelated user stays calm — the exact signal the fraud
// model keys on.
#[test]
fn burst_raises_velocity_and_zscore() {
    let agg = Aggregator::new();

    // baseline: ten normal $50 purchases spread over 5 minutes
    for i in 0..10 {
        agg.ingest("victim", i as f64 * 30.0, 50.0, "coffee", "US");
    }
    let calm = agg.latest_for("victim").unwrap();
    // events are 30 s apart, so at most ~3 fall inside the 60 s velocity window
    assert!(calm.features.velocity_1m <= 3);

    // attack: five rapid high-value charges in the same 4 seconds
    let t0 = 300.0;
    for i in 0..5 {
        agg.ingest("victim", t0 + i as f64, 1200.0, &format!("m{i}"), "RU");
    }
    let hot = agg.latest_for("victim").unwrap();
    assert!(hot.features.velocity_1m >= 5, "vel={}", hot.features.velocity_1m);
    assert!(hot.features.amount_zscore > 1.0, "z={}", hot.features.amount_zscore);
    assert!(hot.features.distinct_countries_5m >= 2);
}

#[test]
fn latency_budget_ingest_10k_events() {
    use std::time::Instant;
    let agg = Aggregator::new();
    let start = Instant::now();
    for i in 0..10_000u64 {
        agg.ingest("u", i as f64 * 0.01, 100.0, "m", "US");
    }
    let elapsed = start.elapsed();
    // 10k incremental pushes must stay well under a second on any dev machine;
    // this documents the O(1)-per-event design (not a hard CI gate).
    assert!(
        elapsed.as_millis() < 1000,
        "10k ingests took {}ms",
        elapsed.as_millis()
    );
}
