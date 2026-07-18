package config

import "os"

// Config holds every tunable the gateway reads from the environment. Sensible
// offline defaults let it run with no flags at all.
type Config struct {
	HTTPAddr   string // where the ingest API + SSE stream listen
	TCPAddr    string // newline-delimited raw transaction feed
	ComputeURL string // Rust feature compute service
	InferURL   string // Python inference service
	APIKey     string // required X-API-Key on /ingest ("" disables auth)
	Synth      bool   // if true, run the built-in load generator
}

func getenv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// Load reads configuration from the environment.
func Load() Config {
	return Config{
		HTTPAddr:   getenv("FEASTREAM_ADDR", ":8080"),
		TCPAddr:    getenv("FEASTREAM_TCP_ADDR", ":9101"),
		ComputeURL: getenv("FEASTREAM_COMPUTE_URL", "http://localhost:8091"),
		InferURL:   getenv("FEASTREAM_INFER_URL", "http://localhost:8000"),
		APIKey:     os.Getenv("FEASTREAM_API_KEY"),
		Synth:      os.Getenv("FEASTREAM_SYNTH") == "1",
	}
}
