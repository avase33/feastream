"use client";

import { useEffect, useRef, useState } from "react";

const GATEWAY =
  process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8080";

type Score = {
  txn_id: string;
  user_id: string;
  ts: number;
  fraud_probability: number;
  decision: string;
  top_reasons: string[];
  latency_ms: number;
};

type Tick = {
  type: "tick";
  ts: number;
  ingest_rate: number;
  p50_latency_ms: number;
  p99_latency_ms: number;
  dropped: number;
};

type AlertMsg = { type: "alert"; ts: number; alert: Score };

const MAX_POINTS = 120;
const MAX_ALERTS = 40;

function decisionColor(d: string): string {
  if (d === "block") return "#ff5c6c";
  if (d === "review") return "#ffb454";
  return "#4ec9b0";
}

export default function Cockpit() {
  const [connected, setConnected] = useState(false);
  const [rate, setRate] = useState(0);
  const [p50, setP50] = useState(0);
  const [p99, setP99] = useState(0);
  const [dropped, setDropped] = useState(0);
  const [alerts, setAlerts] = useState<Score[]>([]);
  const [history, setHistory] = useState<number[]>([]);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // --- live stream -------------------------------------------------------
  useEffect(() => {
    const es = new EventSource(`${GATEWAY}/stream`);
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.onmessage = (e: MessageEvent) => {
      try {
        const msg = JSON.parse(e.data) as Tick | AlertMsg;
        if (msg.type === "tick") {
          setRate(msg.ingest_rate);
          setP50(msg.p50_latency_ms);
          setP99(msg.p99_latency_ms);
          setDropped(msg.dropped);
          setHistory((h) => {
            const next = [...h, msg.p99_latency_ms];
            return next.length > MAX_POINTS ? next.slice(-MAX_POINTS) : next;
          });
        } else if (msg.type === "alert") {
          setAlerts((a) => [msg.alert, ...a].slice(0, MAX_ALERTS));
        }
      } catch {
        /* ignore malformed frames */
      }
    };
    return () => es.close();
  }, []);

  // --- latency sparkline -------------------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    // 10 ms SLA line
    const maxV = Math.max(12, ...history);
    const yFor = (v: number) => H - (v / maxV) * (H - 8) - 4;
    ctx.strokeStyle = "#30363d";
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(0, yFor(10));
    ctx.lineTo(W, yFor(10));
    ctx.stroke();
    ctx.setLineDash([]);

    if (history.length > 1) {
      ctx.strokeStyle = "#58a6ff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      history.forEach((v, i) => {
        const x = (i / (MAX_POINTS - 1)) * W;
        const y = yFor(v);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }
  }, [history]);

  return (
    <main style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <h1 style={{ fontSize: 22, margin: 0 }}>feastream · fraud cockpit</h1>
        <span style={{ color: connected ? "#4ec9b0" : "#ff5c6c" }}>
          {connected ? "● live" : "○ offline"}
        </span>
      </header>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 12,
          marginTop: 20,
        }}
      >
        <Metric label="ingest / sec" value={rate.toLocaleString()} />
        <Metric label="p50 latency" value={`${p50.toFixed(1)} ms`} />
        <Metric
          label="p99 latency"
          value={`${p99.toFixed(1)} ms`}
          warn={p99 > 10}
        />
        <Metric label="dropped" value={dropped.toLocaleString()} warn={dropped > 0} />
      </section>

      <section style={{ marginTop: 24 }}>
        <h2 style={{ fontSize: 14, color: "#8b949e" }}>
          p99 latency (dashed line = 10 ms SLA)
        </h2>
        <canvas
          ref={canvasRef}
          width={1050}
          height={140}
          style={{
            width: "100%",
            background: "#0d1117",
            border: "1px solid #30363d",
            borderRadius: 8,
          }}
        />
      </section>

      <section style={{ marginTop: 24 }}>
        <h2 style={{ fontSize: 14, color: "#8b949e" }}>
          fraud alerts ({alerts.length})
        </h2>
        <div style={{ border: "1px solid #30363d", borderRadius: 8 }}>
          {alerts.length === 0 && (
            <p style={{ padding: 16, color: "#8b949e" }}>
              no alerts yet — waiting for review/block decisions…
            </p>
          )}
          {alerts.map((a, i) => (
            <div
              key={`${a.txn_id}-${i}`}
              style={{
                display: "grid",
                gridTemplateColumns: "90px 90px 80px 1fr 70px",
                gap: 8,
                padding: "8px 12px",
                borderTop: i ? "1px solid #21262d" : "none",
                alignItems: "center",
              }}
            >
              <span style={{ color: decisionColor(a.decision), fontWeight: 700 }}>
                {a.decision.toUpperCase()}
              </span>
              <span>{a.user_id}</span>
              <span>{(a.fraud_probability * 100).toFixed(0)}%</span>
              <span style={{ color: "#8b949e", fontSize: 13 }}>
                {a.top_reasons.join("  ·  ")}
              </span>
              <span style={{ color: "#8b949e", textAlign: "right" }}>
                {a.latency_ms.toFixed(1)}ms
              </span>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

function Metric({
  label,
  value,
  warn,
}: {
  label: string;
  value: string;
  warn?: boolean;
}) {
  return (
    <div
      style={{
        background: "#0d1117",
        border: `1px solid ${warn ? "#ff5c6c" : "#30363d"}`,
        borderRadius: 8,
        padding: 16,
      }}
    >
      <div style={{ color: "#8b949e", fontSize: 12 }}>{label}</div>
      <div
        style={{
          fontSize: 26,
          marginTop: 6,
          color: warn ? "#ff5c6c" : "#e6edf3",
        }}
      >
        {value}
      </div>
    </div>
  );
}
