from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from .metrics import percentile

LOG_PATH = Path(os.getenv("LOG_PATH", "data/logs.jsonl"))


def parse_timestamp(ts_str: str) -> datetime | None:
    if not ts_str:
        return None
    try:
        # Normalize ISO strings
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)
    except Exception:
        return None


def get_dashboard_metrics(time_range_minutes: int = 60) -> dict[str, Any]:
    if not LOG_PATH.exists():
        records = []
    else:
        records = []
        for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=time_range_minutes)

    # Filter by time if ts exists, otherwise include all if recent
    filtered: list[dict[str, Any]] = []
    for r in records:
        ts = parse_timestamp(r.get("ts", ""))
        if ts is None or ts >= cutoff:
            filtered.append(r)

    # If filtered is empty but records exist, use records to ensure dashboard has viewable data
    dataset = filtered if filtered else records

    req_received = [r for r in dataset if r.get("event") == "request_received"]
    resp_sent = [r for r in dataset if r.get("event") == "response_sent"]
    req_failed = [r for r in dataset if r.get("event") == "request_failed"]

    # 1. Latency Panel
    latencies = [int(r["latency_ms"]) for r in resp_sent if "latency_ms" in r]
    ttfts = [int(r["ttft_ms"]) for r in resp_sent if "ttft_ms" in r]

    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)
    ttft_p95 = percentile(ttfts, 95)

    # 2. Traffic Panel
    traffic_count = len(req_received)
    minute_buckets_traffic: dict[str, int] = defaultdict(int)
    for r in req_received:
        ts = parse_timestamp(r.get("ts", ""))
        minute_key = ts.strftime("%H:%M") if ts else "recent"
        minute_buckets_traffic[minute_key] += 1
    
    rate_per_minute = round(traffic_count / max(1, min(time_range_minutes, len(minute_buckets_traffic) or 1)), 2)

    # 3. Errors Panel
    total_received = max(1, len(req_received))
    error_rate_pct = round((len(req_failed) / total_received) * 100, 2)
    
    error_breakdown: Counter[str] = Counter()
    for r in req_failed:
        err_type = r.get("error_type", "UnknownError")
        error_breakdown[err_type] += 1

    tool_events = [r for r in dataset if r.get("tool_success") is not None]
    tool_success_count = sum(1 for r in tool_events if r.get("tool_success") is True)
    tool_success_rate_pct = round((tool_success_count / max(1, len(tool_events))) * 100, 2) if tool_events else 100.0

    # 4. Cost Panel
    costs = [float(r["cost_usd"]) for r in resp_sent if "cost_usd" in r]
    total_cost = round(sum(costs), 4)

    minute_buckets_cost: dict[str, float] = defaultdict(float)
    for r in resp_sent:
        ts = parse_timestamp(r.get("ts", ""))
        minute_key = ts.strftime("%H:%M") if ts else "recent"
        minute_buckets_cost[minute_key] += float(r.get("cost_usd", 0.0))

    # 5. Tokens Panel
    tokens_in = sum(int(r.get("tokens_in", 0)) for r in resp_sent)
    tokens_out = sum(int(r.get("tokens_out", 0)) for r in resp_sent)
    total_tokens = tokens_in + tokens_out

    # 6. Quality Panel
    quality_scores = [float(r["quality_score"]) for r in resp_sent if "quality_score" in r]
    quality_mean = round(sum(quality_scores) / max(1, len(quality_scores)), 2) if quality_scores else 0.85

    # Time series points for timeline charts (last 15 records or minutes)
    timeline_labels = []
    timeline_latencies = []
    timeline_qualities = []
    for r in resp_sent[-20:]:
        ts = parse_timestamp(r.get("ts", ""))
        label = ts.strftime("%H:%M:%S") if ts else f"req-{len(timeline_labels)+1}"
        timeline_labels.append(label)
        timeline_latencies.append(r.get("latency_ms", 0))
        timeline_qualities.append(r.get("quality_score", 0.8))

    traffic_time_labels = sorted(minute_buckets_traffic.keys())
    traffic_time_values = [minute_buckets_traffic[k] for k in traffic_time_labels]

    cost_time_labels = sorted(minute_buckets_cost.keys())
    cost_time_values = [round(minute_buckets_cost[k], 4) for k in cost_time_labels]

    return {
        "time_range_minutes": time_range_minutes,
        "total_records": len(dataset),
        "refreshed_at": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "latency": {
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "ttft_p95": ttft_p95,
            "threshold_p95": 3000,
            "unit": "ms",
            "status": "PASS" if p95 <= 3000 else "BREACH",
            "timeline_labels": timeline_labels,
            "timeline_values": timeline_latencies,
        },
        "traffic": {
            "count": traffic_count,
            "rate_per_minute": rate_per_minute,
            "threshold_rate": 1.0,
            "unit": "requests_per_minute",
            "status": "PASS" if rate_per_minute >= 1.0 else "WARN",
            "time_labels": traffic_time_labels,
            "time_values": traffic_time_values,
        },
        "errors": {
            "error_rate_pct": error_rate_pct,
            "threshold_error_rate_pct": 2.0,
            "tool_success_rate_pct": tool_success_rate_pct,
            "threshold_tool_success_rate_pct": 90.0,
            "breakdown": dict(error_breakdown) if error_breakdown else {"None": 0},
            "unit": "percent",
            "status": "PASS" if error_rate_pct <= 2.0 and tool_success_rate_pct >= 90.0 else "BREACH",
        },
        "cost": {
            "total": total_cost,
            "threshold_total": 2.5,
            "unit": "usd",
            "status": "PASS" if total_cost <= 2.5 else "BREACH",
            "time_labels": cost_time_labels,
            "time_values": cost_time_values,
        },
        "tokens": {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "total": total_tokens,
            "threshold_total": 50000,
            "unit": "tokens",
            "status": "PASS" if total_tokens <= 50000 else "BREACH",
        },
        "quality": {
            "mean": quality_mean,
            "threshold_mean": 0.75,
            "unit": "score_0_to_1",
            "status": "PASS" if quality_mean >= 0.75 else "BREACH",
            "timeline_labels": timeline_labels,
            "timeline_values": timeline_qualities,
        },
    }


def render_dashboard_html(metrics: dict[str, Any]) -> str:
    m = metrics
    lat = m["latency"]
    traf = m["traffic"]
    err = m["errors"]
    cost = m["cost"]
    tok = m["tokens"]
    qual = m["quality"]

    def badge(status: str) -> str:
        if status == "PASS":
            return '<span class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">PASS</span>'
        elif status == "WARN":
            return '<span class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/30">WARN</span>'
        return '<span class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/20 text-rose-400 border border-rose-500/30">BREACH</span>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>K4-L3B Day 13 Monitoring & LLMOps Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <meta http-equiv="refresh" content="30">
  <style>
    body {{ background-color: #0b0f19; color: #f1f5f9; font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; }}
    .panel-card {{ background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; }}
    .panel-card:hover {{ border-color: rgba(255, 255, 255, 0.15); }}
  </style>
</head>
<body class="p-6 min-h-screen">
  <!-- Top Navigation & Header -->
  <header class="max-w-7xl mx-auto mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800 pb-4">
    <div>
      <div class="flex items-center gap-3">
        <h1 class="text-2xl font-bold tracking-tight text-white">K4-L3B Day 13 Monitoring &amp; LLMOps</h1>
        <span class="px-2.5 py-1 rounded bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 text-xs font-mono font-medium">LIVE RUNTIME</span>
      </div>
      <p class="text-sm text-slate-400 mt-1">Source: <code class="text-indigo-300 font-mono">data/logs.jsonl</code> | Contract: <code class="text-slate-300 font-mono">config/dashboard.yaml</code></p>
    </div>
    <div class="flex items-center gap-4 text-sm">
      <div class="bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700/60 flex items-center gap-2">
        <span class="text-slate-400">Time Range:</span>
        <span class="font-semibold text-white">Last {m["time_range_minutes"]} Minutes</span>
      </div>
      <div class="bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700/60 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
        <span class="text-slate-400">Auto-refresh:</span>
        <span class="font-mono text-emerald-400 font-medium">30s</span>
      </div>
      <button onclick="location.reload()" class="bg-indigo-600 hover:bg-indigo-500 text-white font-medium px-4 py-1.5 rounded-lg transition-colors shadow-sm">
        Refresh Now
      </button>
    </div>
  </header>

  <!-- Main 6 Panels Grid -->
  <main class="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

    <!-- PANEL 1: Latency -->
    <div class="panel-card p-5 flex flex-col justify-between shadow-xl">
      <div>
        <div class="flex items-center justify-between mb-3">
          <div>
            <span class="text-xs uppercase tracking-wider text-slate-400 font-semibold">Panel 1 &bull; ID: latency</span>
            <h2 class="text-lg font-bold text-white">Latency percentiles and TTFT</h2>
          </div>
          {badge(lat["status"])}
        </div>
        <div class="grid grid-cols-4 gap-2 my-3 text-center">
          <div class="bg-slate-900/60 p-2 rounded-lg border border-slate-800">
            <div class="text-xs text-slate-400 font-medium">P50</div>
            <div class="text-lg font-bold text-white font-mono mt-0.5">{lat["p50"]}<span class="text-xs text-slate-400 ml-0.5">ms</span></div>
          </div>
          <div class="bg-slate-900/60 p-2 rounded-lg border border-slate-800">
            <div class="text-xs text-slate-400 font-medium">P95</div>
            <div class="text-lg font-bold text-indigo-400 font-mono mt-0.5">{lat["p95"]}<span class="text-xs text-slate-400 ml-0.5">ms</span></div>
          </div>
          <div class="bg-slate-900/60 p-2 rounded-lg border border-slate-800">
            <div class="text-xs text-slate-400 font-medium">P99</div>
            <div class="text-lg font-bold text-amber-400 font-mono mt-0.5">{lat["p99"]}<span class="text-xs text-slate-400 ml-0.5">ms</span></div>
          </div>
          <div class="bg-slate-900/60 p-2 rounded-lg border border-slate-800">
            <div class="text-xs text-slate-400 font-medium">TTFT P95</div>
            <div class="text-lg font-bold text-emerald-400 font-mono mt-0.5">{lat["ttft_p95"]}<span class="text-xs text-slate-400 ml-0.5">ms</span></div>
          </div>
        </div>
        <div class="h-40 w-full mt-2">
          <canvas id="chart-latency"></canvas>
        </div>
      </div>
      <div class="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
        <span>Unit: <strong class="text-slate-300">{lat["unit"]}</strong></span>
        <span>Threshold: <strong class="text-rose-400">P95 &le; {lat["threshold_p95"]} ms</strong></span>
      </div>
    </div>

    <!-- PANEL 2: Traffic -->
    <div class="panel-card p-5 flex flex-col justify-between shadow-xl">
      <div>
        <div class="flex items-center justify-between mb-3">
          <div>
            <span class="text-xs uppercase tracking-wider text-slate-400 font-semibold">Panel 2 &bull; ID: traffic</span>
            <h2 class="text-lg font-bold text-white">Request traffic</h2>
          </div>
          {badge(traf["status"])}
        </div>
        <div class="grid grid-cols-2 gap-3 my-3">
          <div class="bg-slate-900/60 p-3 rounded-lg border border-slate-800">
            <div class="text-xs text-slate-400">Total Requests</div>
            <div class="text-2xl font-bold text-white font-mono mt-1">{traf["count"]}</div>
          </div>
          <div class="bg-slate-900/60 p-3 rounded-lg border border-slate-800">
            <div class="text-xs text-slate-400">Rate / Minute</div>
            <div class="text-2xl font-bold text-indigo-400 font-mono mt-1">{traf["rate_per_minute"]} <span class="text-xs text-slate-400">rpm</span></div>
          </div>
        </div>
        <div class="h-40 w-full mt-2">
          <canvas id="chart-traffic"></canvas>
        </div>
      </div>
      <div class="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
        <span>Unit: <strong class="text-slate-300">{traf["unit"]}</strong></span>
        <span>Threshold: <strong class="text-emerald-400">rate &ge; {traf["threshold_rate"]} rpm</strong></span>
      </div>
    </div>

    <!-- PANEL 3: Errors -->
    <div class="panel-card p-5 flex flex-col justify-between shadow-xl">
      <div>
        <div class="flex items-center justify-between mb-3">
          <div>
            <span class="text-xs uppercase tracking-wider text-slate-400 font-semibold">Panel 3 &bull; ID: errors</span>
            <h2 class="text-lg font-bold text-white">Error rate and retrieval success</h2>
          </div>
          {badge(err["status"])}
        </div>
        <div class="grid grid-cols-2 gap-3 my-3">
          <div class="bg-slate-900/60 p-3 rounded-lg border border-slate-800">
            <div class="text-xs text-slate-400">API Error Rate</div>
            <div class="text-2xl font-bold {'text-rose-400' if err['error_rate_pct'] > 2 else 'text-emerald-400'} font-mono mt-1">{err["error_rate_pct"]}%</div>
          </div>
          <div class="bg-slate-900/60 p-3 rounded-lg border border-slate-800">
            <div class="text-xs text-slate-400">Retrieval Success</div>
            <div class="text-2xl font-bold text-cyan-400 font-mono mt-1">{err["tool_success_rate_pct"]}%</div>
          </div>
        </div>
        <div class="h-40 w-full mt-2 flex flex-col justify-center bg-slate-900/40 p-3 rounded-lg border border-slate-800/60">
          <div class="text-xs text-slate-400 font-medium mb-2">Error Breakdown:</div>
          <div class="space-y-1.5 text-xs font-mono">
            {''.join([f'<div class="flex justify-between items-center bg-slate-800/50 px-2 py-1 rounded"><span>{k}</span><span class="text-slate-300 font-bold">{v}</span></div>' for k, v in err["breakdown"].items()])}
          </div>
        </div>
      </div>
      <div class="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
        <span>Unit: <strong class="text-slate-300">{err["unit"]}</strong></span>
        <span>Threshold: <strong class="text-rose-400">Error &le; {err["threshold_error_rate_pct"]}%</strong> &bull; <strong class="text-cyan-400">Retrieval &ge; 90%</strong></span>
      </div>
    </div>

    <!-- PANEL 4: Cost -->
    <div class="panel-card p-5 flex flex-col justify-between shadow-xl">
      <div>
        <div class="flex items-center justify-between mb-3">
          <div>
            <span class="text-xs uppercase tracking-wider text-slate-400 font-semibold">Panel 4 &bull; ID: cost</span>
            <h2 class="text-lg font-bold text-white">Cost over time</h2>
          </div>
          {badge(cost["status"])}
        </div>
        <div class="bg-slate-900/60 p-3 rounded-lg border border-slate-800 my-3">
          <div class="text-xs text-slate-400">Cumulative Cost (Window)</div>
          <div class="text-2xl font-bold text-amber-400 font-mono mt-1">${cost["total"]:.4f} <span class="text-xs text-slate-400">USD</span></div>
        </div>
        <div class="h-40 w-full mt-2">
          <canvas id="chart-cost"></canvas>
        </div>
      </div>
      <div class="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
        <span>Unit: <strong class="text-slate-300">{cost["unit"]}</strong></span>
        <span>Threshold: <strong class="text-amber-400">Total &le; ${cost["threshold_total"]} USD</strong></span>
      </div>
    </div>

    <!-- PANEL 5: Tokens -->
    <div class="panel-card p-5 flex flex-col justify-between shadow-xl">
      <div>
        <div class="flex items-center justify-between mb-3">
          <div>
            <span class="text-xs uppercase tracking-wider text-slate-400 font-semibold">Panel 5 &bull; ID: tokens</span>
            <h2 class="text-lg font-bold text-white">Input and output tokens</h2>
          </div>
          {badge(tok["status"])}
        </div>
        <div class="grid grid-cols-3 gap-2 my-3 text-center">
          <div class="bg-slate-900/60 p-2 rounded-lg border border-slate-800">
            <div class="text-xs text-slate-400 font-medium">Input</div>
            <div class="text-base font-bold text-blue-400 font-mono mt-0.5">{tok["tokens_in"]:,}</div>
          </div>
          <div class="bg-slate-900/60 p-2 rounded-lg border border-slate-800">
            <div class="text-xs text-slate-400 font-medium">Output</div>
            <div class="text-base font-bold text-purple-400 font-mono mt-0.5">{tok["tokens_out"]:,}</div>
          </div>
          <div class="bg-slate-900/60 p-2 rounded-lg border border-slate-800">
            <div class="text-xs text-slate-400 font-medium">Total</div>
            <div class="text-base font-bold text-white font-mono mt-0.5">{tok["total"]:,}</div>
          </div>
        </div>
        <div class="h-40 w-full mt-2">
          <canvas id="chart-tokens"></canvas>
        </div>
      </div>
      <div class="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
        <span>Unit: <strong class="text-slate-300">{tok["unit"]}</strong></span>
        <span>Threshold: <strong class="text-purple-400">Total &le; {tok["threshold_total"]:,}</strong></span>
      </div>
    </div>

    <!-- PANEL 6: Quality -->
    <div class="panel-card p-5 flex flex-col justify-between shadow-xl">
      <div>
        <div class="flex items-center justify-between mb-3">
          <div>
            <span class="text-xs uppercase tracking-wider text-slate-400 font-semibold">Panel 6 &bull; ID: quality</span>
            <h2 class="text-lg font-bold text-white">Quality proxy</h2>
          </div>
          {badge(qual["status"])}
        </div>
        <div class="bg-slate-900/60 p-3 rounded-lg border border-slate-800 my-3">
          <div class="text-xs text-slate-400">Average Quality Score</div>
          <div class="text-2xl font-bold text-emerald-400 font-mono mt-1">{qual["mean"]:.2f} <span class="text-xs text-slate-400">/ 1.00</span></div>
        </div>
        <div class="h-40 w-full mt-2">
          <canvas id="chart-quality"></canvas>
        </div>
      </div>
      <div class="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
        <span>Unit: <strong class="text-slate-300">{qual["unit"]}</strong></span>
        <span>Threshold: <strong class="text-emerald-400">mean &ge; {qual["threshold_mean"]}</strong></span>
      </div>
    </div>

  </main>

  <footer class="max-w-7xl mx-auto mt-8 text-center text-xs text-slate-500">
    Last Refreshed: {m["refreshed_at"]} &bull; K4-L3B Monitoring &amp; LLMOps
  </footer>

  <script>
    const chartDefaults = {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ grid: {{ display: false, color: '#334155' }}, ticks: {{ color: '#94a3b8', font: {{ size: 10 }} }} }},
        y: {{ grid: {{ color: 'rgba(51, 65, 85, 0.4)' }}, ticks: {{ color: '#94a3b8', font: {{ size: 10 }} }} }}
      }}
    }};

    // Latency Chart
    new Chart(document.getElementById('chart-latency'), {{
      type: 'line',
      data: {{
        labels: {json.dumps(lat["timeline_labels"][-10:])},
        datasets: [
          {{
            label: 'Latency (ms)',
            data: {json.dumps(lat["timeline_values"][-10:])},
            borderColor: '#818cf8',
            backgroundColor: 'rgba(129, 140, 248, 0.15)',
            borderWidth: 2,
            tension: 0.3,
            fill: true
          }},
          {{
            label: 'SLO Threshold (3000ms)',
            data: Array({len(lat["timeline_labels"][-10:])}).fill(3000),
            borderColor: 'rgba(244, 63, 94, 0.8)',
            borderWidth: 1.5,
            borderDash: [4, 4],
            pointRadius: 0
          }}
        ]
      }},
      options: chartDefaults
    }});

    // Traffic Chart
    new Chart(document.getElementById('chart-traffic'), {{
      type: 'bar',
      data: {{
        labels: {json.dumps(traf["time_labels"][-8:])},
        datasets: [{{
          label: 'Requests',
          data: {json.dumps(traf["time_values"][-8:])},
          backgroundColor: '#38bdf8',
          borderRadius: 4
        }}]
      }},
      options: chartDefaults
    }});

    // Cost Chart
    new Chart(document.getElementById('chart-cost'), {{
      type: 'line',
      data: {{
        labels: {json.dumps(cost["time_labels"][-8:])},
        datasets: [{{
          label: 'Cost ($)',
          data: {json.dumps(cost["time_values"][-8:])},
          borderColor: '#fbbf24',
          backgroundColor: 'rgba(251, 191, 36, 0.15)',
          borderWidth: 2,
          fill: true
        }}]
      }},
      options: chartDefaults
    }});

    // Tokens Bar Chart
    new Chart(document.getElementById('chart-tokens'), {{
      type: 'bar',
      data: {{
        labels: ['Input Tokens', 'Output Tokens'],
        datasets: [{{
          data: [{tok["tokens_in"]}, {tok["tokens_out"]}],
          backgroundColor: ['#60a5fa', '#c084fc'],
          borderRadius: 6
        }}]
      }},
      options: chartDefaults
    }});

    // Quality Chart
    new Chart(document.getElementById('chart-quality'), {{
      type: 'line',
      data: {{
        labels: {json.dumps(qual["timeline_labels"][-10:])},
        datasets: [
          {{
            label: 'Quality Score',
            data: {json.dumps(qual["timeline_values"][-10:])},
            borderColor: '#34d399',
            backgroundColor: 'rgba(52, 211, 153, 0.15)',
            borderWidth: 2,
            tension: 0.3,
            fill: true
          }},
          {{
            label: 'Quality Target (0.75)',
            data: Array({len(qual["timeline_labels"][-10:])}).fill(0.75),
            borderColor: 'rgba(251, 191, 36, 0.8)',
            borderWidth: 1.5,
            borderDash: [4, 4],
            pointRadius: 0
          }}
        ]
      }},
      options: {{
        ...chartDefaults,
        scales: {{
          ...chartDefaults.scales,
          y: {{ ...chartDefaults.scales.y, min: 0, max: 1 }}
        }}
      }}
    }});
  </script>
</body>
</html>"""
