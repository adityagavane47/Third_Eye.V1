/**
 * ThreatActivityGraph.tsx — Cyberpunk Threat Activity Area Chart
 * Displays attack frequency over a rolling time window using Recharts.
 */

import { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
// Custom tooltip prop shape — avoids Recharts internal type version drift
interface ChartTooltipProps {
  active?: boolean;
  payload?: Array<{ value: number | string }>;
  label?: string;
}

// ── Types ───────────────────────────────────────────────────────

export interface ThreatDataPoint {
  time: string;   // e.g. "14:00", "14:05"
  attacks: number;
}

interface ThreatActivityGraphProps {
  data?: ThreatDataPoint[];
  /** Optional title shown above the chart */
  title?: string;
  /** Height of the chart area in px (default 180) */
  height?: number;
  /** Called when the user clicks the expand button */
  onExpand?: () => void;
}

// ── Demo data generator (used when no data prop is supplied) ────

function generateDemoData(): ThreatDataPoint[] {
  const now = new Date();
  return Array.from({ length: 20 }, (_, i) => {
    const t = new Date(now.getTime() - (19 - i) * 3 * 60 * 1000);
    const h = t.getHours().toString().padStart(2, "0");
    const m = t.getMinutes().toString().padStart(2, "0");
    // Simulate a burst pattern
    const base = 2 + Math.random() * 4;
    const spike = i > 13 && i < 17 ? Math.random() * 18 : 0;
    return { time: `${h}:${m}`, attacks: Math.round(base + spike) };
  });
}

// ── Custom Tooltip ───────────────────────────────────────────────

function CyberpunkTooltip({ active, payload, label }: ChartTooltipProps) {
  if (!active || !payload?.length) return null;
  const value = payload[0]?.value ?? 0;

  return (
    <div
      style={{
        background: "rgba(2, 6, 23, 0.97)",
        border: "1px solid rgba(239, 68, 68, 0.7)",
        borderRadius: 6,
        padding: "8px 14px",
        boxShadow: "0 0 16px rgba(239, 68, 68, 0.25), 0 4px 24px rgba(0,0,0,0.8)",
        fontFamily: "'JetBrains Mono', 'Courier New', monospace",
      }}
    >
      <div style={{ fontSize: 9, color: "#ef4444", letterSpacing: "0.15em", marginBottom: 4 }}>
        ◉ THREAT TERMINAL
      </div>
      <div style={{ fontSize: 11, color: "#64748b", marginBottom: 2 }}>
        TIME: <span style={{ color: "#94a3b8" }}>{label}</span>
      </div>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#ef4444" }}>
        {value}{" "}
        <span style={{ fontSize: 10, fontWeight: 400, color: "#ef4444", opacity: 0.7 }}>
          ATTACKS
        </span>
      </div>
    </div>
  );
}

// ── Main Component ───────────────────────────────────────────────

export default function ThreatActivityGraph({
  data,
  title = "THREAT ACTIVITY",
  height = 180,
  onExpand,
}: ThreatActivityGraphProps) {
  const chartData = useMemo(() => data ?? generateDemoData(), [data]);

  return (
    <div
      className="bg-slate-950/50 border border-slate-800 rounded-xl overflow-hidden"
      style={{
        boxShadow:
          "inset 0 0 30px rgba(239,68,68,0.04), 0 4px 24px rgba(0,0,0,0.5)",
      }}
    >
      {/* ── Header ── */}
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <div className="flex items-center gap-2">
          {/* Pulsing live indicator */}
          <span className="relative flex h-2 w-2">
            <span
              className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-500 opacity-50"
            />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500" />
          </span>
          <span
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.14em",
              color: "#ef4444",
            }}
          >
            {title}
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 9,
              color: "#475569",
              letterSpacing: "0.08em",
            }}
          >
            ROLLING · 1H
          </span>
          {onExpand && (
            <button
              onClick={onExpand}
              title="Expand chart"
              style={{
                background: "rgba(239,68,68,0.08)",
                border: "1px solid rgba(239,68,68,0.3)",
                borderRadius: 5,
                color: "#ef4444",
                cursor: "pointer",
                padding: "2px 7px",
                fontSize: 11,
                lineHeight: 1.4,
                fontFamily: "'JetBrains Mono', monospace",
                letterSpacing: "0.06em",
                transition: "background 0.2s",
              }}
              onMouseEnter={(e) =>
                ((e.currentTarget as HTMLButtonElement).style.background =
                  "rgba(239,68,68,0.18)")
              }
              onMouseLeave={(e) =>
                ((e.currentTarget as HTMLButtonElement).style.background =
                  "rgba(239,68,68,0.08)")
              }
            >
              ⛶ EXPAND
            </button>
          )}
        </div>
      </div>

      {/* ── Chart ── */}
      <div style={{ paddingBottom: 4 }}>
        <ResponsiveContainer width="100%" height={height}>
          <AreaChart
            data={chartData}
            margin={{ top: 8, right: 12, left: -20, bottom: 0 }}
          >
            <defs>
              <linearGradient id="threatGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#ef4444" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#ef4444" stopOpacity={0} />
              </linearGradient>
            </defs>

            {/* Subtle grid */}
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(255,255,255,0.04)"
              vertical={false}
            />

            {/* X-Axis: time labels */}
            <XAxis
              dataKey="time"
              axisLine={false}
              tickLine={false}
              tick={{
                fill: "#475569",
                fontSize: 9,
                fontFamily: "'JetBrains Mono', monospace",
              }}
              // Show every 4th tick to avoid crowding
              interval={3}
              dy={4}
            />

            {/* Y-Axis: frequency labels */}
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{
                fill: "#475569",
                fontSize: 9,
                fontFamily: "'JetBrains Mono', monospace",
              }}
              allowDecimals={false}
            />

            {/* Custom cyberpunk tooltip */}
            <Tooltip
              content={<CyberpunkTooltip />}
              cursor={{
                stroke: "rgba(239,68,68,0.4)",
                strokeWidth: 1,
                strokeDasharray: "4 3",
              }}
            />

            {/* Area with monotone curve */}
            <Area
              type="monotone"
              dataKey="attacks"
              stroke="#ef4444"
              strokeWidth={2}
              fill="url(#threatGradient)"
              dot={false}
              activeDot={{
                r: 4,
                fill: "#ef4444",
                stroke: "rgba(239,68,68,0.4)",
                strokeWidth: 6,
              }}
              style={{ filter: "drop-shadow(0 0 6px rgba(239,68,68,0.5))" }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
