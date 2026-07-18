package pipeline

import (
	"testing"
	"time"
)

func TestMetricsPercentiles(t *testing.T) {
	m := NewMetrics(100)
	for i := 1; i <= 100; i++ {
		m.Observe(float64(i))
	}
	p50, p99, _, total := m.Snapshot()
	if total != 100 {
		t.Fatalf("total=%d", total)
	}
	if p50 < 45 || p50 > 55 {
		t.Fatalf("p50 out of range: %v", p50)
	}
	if p99 < 95 {
		t.Fatalf("p99 too low: %v", p99)
	}
}

func TestSynthEmitsBurst(t *testing.T) {
	got := 0
	fraudCountries := map[string]bool{"RU": true, "NG": true, "BR": true}
	sawFraud := false
	stop := make(chan struct{})
	done := make(chan struct{})
	go func() {
		Synth(1, func(tx Transaction) {
			got++
			if fraudCountries[tx.Country] {
				sawFraud = true
			}
			if got >= 400 {
				select {
				case <-stop:
				default:
					close(stop)
				}
			}
		}, stop)
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(30 * time.Second):
		close(stop)
		t.Fatal("synth did not produce enough events in time")
	}
	if got < 400 {
		t.Fatalf("only produced %d events", got)
	}
	if !sawFraud {
		t.Fatal("expected at least one cross-border fraud burst")
	}
}
