// Command feastream-gateway is the ingestion proxy: it authenticates clients,
// absorbs raw transactions over HTTP and a raw TCP feed, applies backpressure
// via an in-memory pub/sub ring, runs each event through the Rust compute +
// Python inference pipeline, and streams operational metrics and fraud alerts
// to the cockpit over Server-Sent Events.
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"feastream/gateway/internal/config"
	"feastream/gateway/internal/hub"
	"feastream/gateway/internal/pipeline"
	"feastream/gateway/internal/ring"
)

type server struct {
	cfg     config.Config
	ring    *ring.Ring
	hub     *hub.Hub
	metrics *pipeline.Metrics
	client  *pipeline.Client
}

// handle pushes one transaction through the pipeline and fans out alerts.
func (s *server) handle(t pipeline.Transaction) (pipeline.Score, error) {
	raw, _ := json.Marshal(t)
	s.ring.Publish(raw)

	sc, err := s.client.Process(t)
	if err != nil {
		return pipeline.Score{}, err
	}
	s.metrics.Observe(sc.LatencyMS)

	if sc.Decision != "allow" {
		frame, _ := json.Marshal(map[string]any{"type": "alert", "ts": sc.TS, "alert": sc})
		s.hub.Broadcast(frame)
	}
	return sc, nil
}

func (s *server) ingestHTTP(w http.ResponseWriter, r *http.Request) {
	if s.cfg.APIKey != "" && r.Header.Get("X-API-Key") != s.cfg.APIKey {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	var t pipeline.Transaction
	if err := json.NewDecoder(r.Body).Decode(&t); err != nil {
		http.Error(w, "bad json", http.StatusBadRequest)
		return
	}
	sc, err := s.handle(t)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(sc)
}

func (s *server) stream(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "streaming unsupported", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	ch := s.hub.Add()
	defer s.hub.Remove(ch)

	for {
		select {
		case <-r.Context().Done():
			return
		case msg, ok := <-ch:
			if !ok {
				return
			}
			fmt.Fprintf(w, "data: %s\n\n", msg)
			flusher.Flush()
		}
	}
}

func (s *server) healthz(w http.ResponseWriter, _ *http.Request) {
	p50, p99, rate, total := s.metrics.Snapshot()
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"status":      "ok",
		"clients":     s.hub.Count(),
		"dropped":     s.ring.Dropped(),
		"total":       total,
		"p50_ms":      p50,
		"p99_ms":      p99,
		"ingest_rate": rate,
	})
}

// tcpFeed reads newline-delimited transactions off the raw feed port.
func (s *server) tcpFeed(ln net.Listener) {
	for {
		conn, err := ln.Accept()
		if err != nil {
			return
		}
		go func(c net.Conn) {
			defer c.Close()
			sc := bufio.NewScanner(c)
			sc.Buffer(make([]byte, 0, 64*1024), 1024*1024)
			for sc.Scan() {
				var t pipeline.Transaction
				if json.Unmarshal(sc.Bytes(), &t) == nil {
					_, _ = s.handle(t)
				}
			}
		}(conn)
	}
}

// ticker broadcasts a periodic metrics frame to the cockpit.
func (s *server) ticker(ctx context.Context) {
	t := time.NewTicker(time.Second)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			p50, p99, rate, _ := s.metrics.Snapshot()
			frame, _ := json.Marshal(map[string]any{
				"type":           "tick",
				"ts":             float64(time.Now().UnixNano()) / 1e9,
				"ingest_rate":    int(rate),
				"p50_latency_ms": p50,
				"p99_latency_ms": p99,
				"dropped":        s.ring.Dropped(),
			})
			s.hub.Broadcast(frame)
		}
	}
}

func main() {
	cfg := config.Load()
	s := &server{
		cfg:     cfg,
		ring:    ring.New(4096),
		hub:     hub.New(),
		metrics: pipeline.NewMetrics(1024),
		client:  pipeline.NewClient(cfg.ComputeURL, cfg.InferURL),
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go s.ticker(ctx)

	if ln, err := net.Listen("tcp", cfg.TCPAddr); err == nil {
		log.Printf("raw transaction feed on %s", cfg.TCPAddr)
		go s.tcpFeed(ln)
	} else {
		log.Printf("tcp feed disabled: %v", err)
	}

	if cfg.Synth {
		stop := make(chan struct{})
		defer close(stop)
		log.Print("synthetic load generator enabled")
		go pipeline.Synth(1, func(t pipeline.Transaction) { _, _ = s.handle(t) }, stop)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("POST /ingest", s.ingestHTTP)
	mux.HandleFunc("GET /stream", s.stream)
	mux.HandleFunc("GET /healthz", s.healthz)

	srv := &http.Server{Addr: cfg.HTTPAddr, Handler: mux}
	go func() {
		log.Printf("feastream-gateway on %s (compute=%s infer=%s)", cfg.HTTPAddr, cfg.ComputeURL, cfg.InferURL)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatal(err)
		}
	}()

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig
	shutCtx, shutCancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer shutCancel()
	_ = srv.Shutdown(shutCtx)
}
