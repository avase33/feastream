// Package pipeline wires a raw transaction through the Rust compute service and
// the Python inference service, and tracks end-to-end latency.
package pipeline

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"sort"
	"sync"
	"time"
)

// Transaction is the raw event ingested from clients (see proto/protocol.md).
type Transaction struct {
	TxnID    string  `json:"txn_id"`
	UserID   string  `json:"user_id"`
	Amount   float64 `json:"amount"`
	Currency string  `json:"currency,omitempty"`
	Merchant string  `json:"merchant"`
	Country  string  `json:"country"`
	TS       float64 `json:"ts,omitempty"`
}

// FeatureVector is what the Rust compute service returns.
type FeatureVector struct {
	UserID   string             `json:"user_id"`
	TS       float64            `json:"ts"`
	Features map[string]float64 `json:"features"`
}

// Score is the Python inference result forwarded to clients and the cockpit.
type Score struct {
	TxnID            string   `json:"txn_id"`
	UserID           string   `json:"user_id"`
	TS               float64  `json:"ts"`
	FraudProbability float64  `json:"fraud_probability"`
	Decision         string   `json:"decision"`
	TopReasons       []string `json:"top_reasons"`
	LatencyMS        float64  `json:"latency_ms"`
}

// Client runs the two-hop pipeline against the compute and inference services.
type Client struct {
	ComputeURL string
	InferURL   string
	HTTP       *http.Client
}

func NewClient(computeURL, inferURL string) *Client {
	return &Client{
		ComputeURL: computeURL,
		InferURL:   inferURL,
		HTTP:       &http.Client{Timeout: 2 * time.Second},
	}
}

func (c *Client) postJSON(url string, in, out any) error {
	body, err := json.Marshal(in)
	if err != nil {
		return err
	}
	resp, err := c.HTTP.Post(url, "application/json", bytes.NewReader(body))
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("%s -> %d: %s", url, resp.StatusCode, string(b))
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

// inferRequest is the FeatureVector plus the originating txn id.
type inferRequest struct {
	TxnID    string             `json:"txn_id"`
	UserID   string             `json:"user_id"`
	TS       float64            `json:"ts"`
	Features map[string]float64 `json:"features"`
}

// Process runs one transaction end to end and returns a scored result.
func (c *Client) Process(t Transaction) (Score, error) {
	start := time.Now()
	var fv FeatureVector
	if err := c.postJSON(c.ComputeURL+"/compute", t, &fv); err != nil {
		return Score{}, fmt.Errorf("compute: %w", err)
	}
	var sc Score
	req := inferRequest{TxnID: t.TxnID, UserID: fv.UserID, TS: fv.TS, Features: fv.Features}
	if err := c.postJSON(c.InferURL+"/score", req, &sc); err != nil {
		return Score{}, fmt.Errorf("infer: %w", err)
	}
	sc.LatencyMS = float64(time.Since(start).Microseconds()) / 1000.0
	if sc.TxnID == "" {
		sc.TxnID = t.TxnID
	}
	return sc, nil
}

// Metrics is a lock-guarded latency reservoir + ingest counter.
type Metrics struct {
	mu        sync.Mutex
	lat       []float64
	cap       int
	total     int64
	lastCount int64
	lastAt    time.Time
}

func NewMetrics(capacity int) *Metrics {
	return &Metrics{cap: capacity, lastAt: time.Now()}
}

func (m *Metrics) Observe(latencyMS float64) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.total++
	if len(m.lat) >= m.cap {
		m.lat = m.lat[1:]
	}
	m.lat = append(m.lat, latencyMS)
}

// Snapshot returns p50, p99 (ms) and the ingest rate (events/sec) since the
// previous call.
func (m *Metrics) Snapshot() (p50, p99, rate float64, total int64) {
	m.mu.Lock()
	defer m.mu.Unlock()
	total = m.total
	now := time.Now()
	dt := now.Sub(m.lastAt).Seconds()
	if dt > 0 {
		rate = float64(m.total-m.lastCount) / dt
	}
	m.lastCount = m.total
	m.lastAt = now

	if len(m.lat) == 0 {
		return 0, 0, rate, total
	}
	cp := make([]float64, len(m.lat))
	copy(cp, m.lat)
	sort.Float64s(cp)
	p50 = percentile(cp, 0.50)
	p99 = percentile(cp, 0.99)
	return p50, p99, rate, total
}

func percentile(sorted []float64, q float64) float64 {
	if len(sorted) == 0 {
		return 0
	}
	idx := int(q * float64(len(sorted)-1))
	return sorted[idx]
}

// Synth drives a realistic offline transaction stream: mostly small normal
// purchases, with an occasional rapid high-value cross-border burst (fraud).
// It calls emit for every generated transaction until stop is closed.
func Synth(seed int64, emit func(Transaction), stop <-chan struct{}) {
	rng := rand.New(rand.NewSource(seed))
	users := []string{"u_001", "u_002", "u_003", "u_004", "u_005"}
	merchants := []string{"coffee", "grocer", "fuel", "stream", "pharma"}
	n := 0
	ticker := time.NewTicker(40 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-stop:
			return
		case <-ticker.C:
			n++
			u := users[rng.Intn(len(users))]
			t := Transaction{
				TxnID:    fmt.Sprintf("t_%06d", n),
				UserID:   u,
				Amount:   round2(20 + rng.Float64()*60),
				Currency: "USD",
				Merchant: merchants[rng.Intn(len(merchants))],
				Country:  "US",
				TS:       float64(time.Now().UnixNano()) / 1e9,
			}
			// ~2% of the time, unleash a five-charge fraud burst on one user
			if rng.Float64() < 0.02 {
				victim := users[rng.Intn(len(users))]
				now := float64(time.Now().UnixNano()) / 1e9
				for i := 0; i < 5; i++ {
					emit(Transaction{
						TxnID:    fmt.Sprintf("t_%06d_f%d", n, i),
						UserID:   victim,
						Amount:   round2(900 + rng.Float64()*600),
						Currency: "USD",
						Merchant: fmt.Sprintf("anon_%d", i),
						Country:  []string{"RU", "NG", "BR"}[rng.Intn(3)],
						TS:       now + float64(i)*0.3,
					})
				}
				continue
			}
			emit(t)
		}
	}
}

func round2(x float64) float64 {
	return float64(int(x*100+0.5)) / 100
}
