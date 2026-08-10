/**
 * Sidebar.tsx — Sentinel Galaxy Forensic Intelligence Panel
 * Framer Motion spring sidebar with staggered child animations.
 */

import React, { useCallback, useState } from "react";
import {
  motion,
  AnimatePresence,
} from "framer-motion";
import type { Variants } from "framer-motion";
import type { GalaxyNode } from "./Galaxy3D";
import ThreatActivityGraph from "./ThreatActivityGraph";

const API_BASE = "";

// ── Types ──────────────────────────────────────────────────────
export interface ForensicReport {
  wallet_address: string;
  risk_level: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  risk_score: number;
  executive_summary: string;
  threat_narrative: string;
  recommended_actions: string[];
  exploit_categories: string[];
}

interface SidebarProps {
  selectedNode: GalaxyNode | null;
  onClose: () => void;
  isExploitDetected?: boolean;
  reportData?: ForensicReport | null;
  onExploreNetwork?: () => void;
}

// ── Color helpers ───────────────────────────────────────────────
const RISK_COLORS: Record<string, string> = {
  CRITICAL: "#FF3B3B",
  HIGH:     "#FF8C00",
  MEDIUM:   "#FFD700",
  LOW:      "#4ADE80",
};

function scoreToColor(score: number): string {
  if (score > 0.85) return "#FF3B3B";
  if (score > 0.65) return "#FF8C00";
  if (score > 0.40) return "#FFD700";
  return "#4ADE80";
}

function scoreToLabel(score: number): string {
  if (score > 0.85) return "CRITICAL";
  if (score > 0.65) return "HIGH";
  if (score > 0.40) return "MEDIUM";
  return "LOW";
}

// ── Animation Variants ─────────────────────────────────────────

const sidebarVariants: Variants = {
  hidden:  { x: "100%", opacity: 0 },
  visible: {
    x: 0,
    opacity: 1,
    transition: {
      type: "spring" as const,
      stiffness: 320,
      damping: 30,
      mass: 0.9,
    },
  },
  exit: {
    x: "100%",
    opacity: 0,
    transition: {
      type: "spring" as const,
      stiffness: 400,
      damping: 38,
    },
  },
};

const containerVariants: Variants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.09,
      delayChildren: 0.18,
    },
  },
};

const itemVariants: Variants = {
  hidden:  { y: 22, opacity: 0 },
  visible: {
    y: 0,
    opacity: 1,
    transition: { type: "spring" as const, stiffness: 260, damping: 24 },
  },
};

// ── SVG Threat Ring ────────────────────────────────────────────
function ThreatRing({ score, color }: { score: number; color: string }) {
  const r = 42;
  const circumference = 2 * Math.PI * r;
  const dash = circumference * score;

  return (
    <div style={{ position: "relative", width: 100, height: 100 }}>
      <svg width={100} height={100} style={{ transform: "rotate(-90deg)" }}>
        {/* Track */}
        <circle
          cx={50} cy={50} r={r}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={7}
        />
        {/* Progress */}
        <motion.circle
          cx={50} cy={50} r={r}
          fill="none"
          stroke={color}
          strokeWidth={7}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference - dash }}
          transition={{ type: "spring", stiffness: 60, damping: 18, delay: 0.3 }}
          style={{ filter: `drop-shadow(0 0 6px ${color})` }}
        />
      </svg>
      <div style={{
        position: "absolute", inset: 0,
        display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center",
      }}>
        <span style={{ color, fontSize: 20, fontWeight: 800, fontFamily: "'JetBrains Mono',monospace", lineHeight: 1 }}>
          {Math.round(score * 100)}
        </span>
        <span style={{ color: "rgba(255,255,255,0.4)", fontSize: 9, letterSpacing: "0.1em", marginTop: 2 }}>RISK %</span>
      </div>
    </div>
  );
}

// ── Pulsing dot ────────────────────────────────────────────────
function LiveDot({ color }: { color: string }) {
  return (
    <span style={{ position: "relative", display: "inline-flex", alignItems: "center" }}>
      <motion.span
        animate={{ scale: [1, 1.8, 1], opacity: [0.7, 0, 0.7] }}
        transition={{ duration: 1.6, repeat: Infinity }}
        style={{
          position: "absolute",
          width: 8, height: 8,
          borderRadius: "50%",
          background: color,
        }}
      />
      <span style={{
        width: 8, height: 8, borderRadius: "50%",
        background: color,
        boxShadow: `0 0 6px ${color}`,
        display: "inline-block",
      }} />
    </span>
  );
}

// ── Main Component ─────────────────────────────────────────────
export default function Sidebar({
  selectedNode,
  onClose,
  isExploitDetected = false,
  reportData,
  onExploreNetwork,
}: SidebarProps) {
  const [report, setReport] = useState<ForensicReport | null>(reportData ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [txStatus, setTxStatus] = useState<"idle" | "pending" | "success" | "error">("idle");
  const [txHash, setTxHash] = useState<string | null>(null);
  const [expandedGraph, setExpandedGraph] = useState(false);

  const fetchReport = useCallback(async () => {
    if (!selectedNode) return;
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const res = await fetch(`${API_BASE}/api/forensic/report/${selectedNode.address}`);
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      setReport(await res.json());
    } catch (err: unknown) {
      const e = err as Error;
      setError(e?.message ?? "Failed to fetch forensic report");
    } finally {
      setLoading(false);
    }
  }, [selectedNode]);

  const handleShield = useCallback(async () => {
    if (!selectedNode) return;

    // Guard: reject placeholder/invalid addresses before hitting the API
    const isValidAddress = /^0x[0-9a-fA-F]{40}$/.test(selectedNode.address);
    if (!isValidAddress) {
      setTxStatus("error");
      console.error("Shield aborted: invalid address", selectedNode.address);
      return;
    }

    setTxStatus("pending");
    setTxHash(null);
    try {
      const res = await fetch(`${API_BASE}/api/shield/blacklist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          wallet_address: selectedNode.address,
          risk_score:     selectedNode.riskScore,
          reason: `Sentinel manual shield — ${selectedNode.label} at ${(selectedNode.riskScore * 100).toFixed(1)}% risk`,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);

      await fetch(`${API_BASE}/api/graph/flag`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ wallet_address: selectedNode.address, risk_score: selectedNode.riskScore }),
      });

      setTxHash(data.tx_hash ?? null);
      setTxStatus("success");
    } catch (err: unknown) {
      const e = err as Error;
      console.error("Shield failed:", e?.message);
      setTxStatus("error");
    }
  }, [selectedNode]);

  const isOpen = !!selectedNode;
  const riskColor = selectedNode ? scoreToColor(selectedNode.riskScore) : "#4ADE80";
  const riskLabel = selectedNode ? scoreToLabel(selectedNode.riskScore) : "LOW";
  const isCritical = isExploitDetected || (selectedNode?.riskScore ?? 0) > 0.85;

  // Close expanded graph on Escape
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExpandedGraph(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <>
    <AnimatePresence>
      {isOpen && selectedNode && (
        <motion.aside
          key="sidebar"
          variants={sidebarVariants}
          initial="hidden"
          animate="visible"
          exit="exit"
          style={{
            position: "absolute",
            top: 0, right: 0,
            width: 500,
            height: "100%",
            zIndex: 50,
            display: "flex",
            flexDirection: "column",
            background: "rgba(2, 6, 23, 0.88)",
            backdropFilter: "blur(24px)",
            WebkitBackdropFilter: "blur(24px)",
            borderLeft: `1px solid ${isCritical ? "rgba(239,68,68,0.45)" : "rgba(0,212,255,0.18)"}`,
            boxShadow: isCritical
              ? "-8px 0 48px rgba(239,68,68,0.12), -2px 0 12px rgba(0,0,0,0.8)"
              : "-8px 0 48px rgba(0,0,0,0.7)",
            fontFamily: "'Inter', sans-serif",
            overflow: "hidden",
          }}
        >
          {/* ── Animated top accent line ── */}
          <motion.div
            animate={isCritical ? { opacity: [0.6, 1, 0.6] } : { opacity: 1 }}
            transition={{ duration: 1.4, repeat: Infinity }}
            style={{
              height: 2,
              background: isCritical
                ? "linear-gradient(90deg, transparent, #FF3B3B, transparent)"
                : "linear-gradient(90deg, transparent, #00D4FF, transparent)",
            }}
          />

          {/* ── Scrollable body ── */}
          <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden" }}>
            <motion.div
              variants={containerVariants}
              initial="hidden"
              animate="visible"
              style={{ padding: "20px 20px 8px" }}
            >

              {/* ── ITEM 1: Header ── */}
              <motion.div variants={itemVariants} style={s.header}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <LiveDot color={riskColor} />
                    <motion.span
                      animate={isCritical ? { opacity: [1, 0.5, 1] } : {}}
                      transition={{ duration: 1.2, repeat: Infinity }}
                      style={{
                        ...s.riskBadge,
                        background: riskColor + "20",
                        color: riskColor,
                        border: `1px solid ${riskColor}55`,
                      }}
                    >
                      {isCritical ? "⚠ " : "● "}{riskLabel} RISK
                    </motion.span>
                    {isExploitDetected && (
                      <motion.span
                        initial={{ scale: 0.8, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        style={s.exploitTag}
                      >
                        EXPLOIT DETECTED
                      </motion.span>
                    )}
                  </div>
                  <div style={s.walletAddr}>
                    {selectedNode.address.slice(0, 10)}…{selectedNode.address.slice(-6)}
                  </div>
                  <div style={s.labelBadge}>
                    {selectedNode.label.toUpperCase()} &nbsp;·&nbsp;{" "}
                    {selectedNode.flagged ? "🚩 FLAGGED" : "◎ ACTIVE"}
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                  <ThreatRing score={selectedNode.riskScore} color={riskColor} />
                </div>
              </motion.div>

              {/* ── ITEM 2: Stats ── */}
              <motion.div variants={itemVariants} style={s.statsRow}>
                {[
                  { label: "TRANSACTIONS", value: selectedNode.txCount.toLocaleString() },
                  { label: "BALANCE ETH",  value: selectedNode.balanceEth.toFixed(3) },
                  { label: "RISK SCORE",   value: `${(selectedNode.riskScore * 100).toFixed(0)}%`, color: riskColor },
                ].map((stat) => (
                  <div key={stat.label} style={s.statCard}>
                    <div style={{ ...s.statValue, ...(stat.color ? { color: stat.color } : {}) }}>
                      {stat.value}
                    </div>
                    <div style={s.statLabel}>{stat.label}</div>
                  </div>
                ))}
              </motion.div>

              {/* ── ITEM 3: Exploit categories ── */}
              <AnimatePresence>
                {isExploitDetected && report?.exploit_categories && report.exploit_categories.length > 0 && (
                  <motion.div
                    key="cats"
                    variants={itemVariants}
                    initial="hidden"
                    animate="visible"
                    exit={{ opacity: 0, y: -8 }}
                    style={s.catSection}
                  >
                    <div style={s.sectionLabel}>🎯 EXPLOIT CATEGORIES</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                      {report.exploit_categories.map((cat, i) => (
                        <motion.span
                          key={cat}
                          initial={{ scale: 0.7, opacity: 0 }}
                          animate={{ scale: 1, opacity: 1 }}
                          transition={{ delay: i * 0.06 }}
                          style={s.catTag}
                        >
                          {cat}
                        </motion.span>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* ── ITEM 3.5: Explore Network Button ── */}
              {onExploreNetwork && (
                <motion.div variants={itemVariants} style={{ marginBottom: 14 }}>
                  <motion.button
                    onClick={onExploreNetwork}
                    whileHover={{ scale: 1.02, boxShadow: "0 0 20px rgba(124,58,237,0.25)" }}
                    whileTap={{ scale: 0.97 }}
                    style={{
                      width: "100%",
                      background: "linear-gradient(135deg, rgba(124,58,237,0.12), rgba(79,70,229,0.08))",
                      border: "1px solid rgba(124,58,237,0.45)",
                      borderRadius: 10,
                      color: "#A78BFA",
                      cursor: "pointer",
                      padding: "12px 16px",
                      fontSize: 13,
                      fontWeight: 700,
                      fontFamily: "'Inter', sans-serif",
                      letterSpacing: "0.05em",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 8,
                    }}
                  >
                    <span style={{ fontSize: 16 }}>🗺</span>
                    Explore Wallet Network
                    <span style={{ fontSize: 10, color: "rgba(167,139,250,0.6)", marginLeft: 4 }}>1-2 HOP</span>
                  </motion.button>
                </motion.div>
              )}

              {/* ── ITEM 3.6: Threat Activity Graph ── */}
              <motion.div variants={itemVariants} style={{ marginBottom: 16 }}>
                <ThreatActivityGraph height={160} onExpand={() => setExpandedGraph(true)} />
              </motion.div>

              {/* ── ITEM 4: AI Analysis ── */}
              <motion.div variants={itemVariants} style={s.section}>
                <div style={s.sectionHeader}>
                  <span>🔍 FORENSIC INTELLIGENCE</span>
                  <button
                    onClick={fetchReport}
                    disabled={loading}
                    style={s.analyzeBtn}
                  >
                    {loading ? (
                      <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <motion.span
                          animate={{ rotate: 360 }}
                          transition={{ repeat: Infinity, duration: 0.8, ease: "linear" }}
                          style={{ display: "inline-block" }}
                        >
                          ⟳
                        </motion.span>
                        Analyzing…
                      </span>
                    ) : "Run AI Analysis"}
                  </button>
                </div>

                {error && <div style={s.errorBox}>{error}</div>}

                {/* ── ITEM 5: AI Narrative ── */}
                <AnimatePresence mode="wait">
                  {report ? (
                    <motion.div
                      key="report"
                      initial={{ opacity: 0, y: 16 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -16 }}
                      transition={{ type: "spring", stiffness: 240, damping: 22 }}
                    >
                      <motion.div
                        initial={{ scaleX: 0 }}
                        animate={{ scaleX: 1 }}
                        transition={{ type: "spring" as const, stiffness: 200, damping: 20 }}
                        style={{
                          ...s.riskBanner,
                          background: (RISK_COLORS[report.risk_level] ?? "#94A3B8") + "18",
                          borderColor: RISK_COLORS[report.risk_level] ?? "#94A3B8",
                          color: RISK_COLORS[report.risk_level] ?? "#94A3B8",
                          originX: 0,
                        }}
                      >
                        ⚠ {report.risk_level} RISK — {(report.risk_score * 100).toFixed(1)}%
                      </motion.div>

                      <p style={s.summaryText}>{report.executive_summary}</p>

                      <div style={s.narrativeBox}>
                        <p style={s.narrativeText}>{report.threat_narrative}</p>
                      </div>

                      {report.recommended_actions.length > 0 && (
                        <motion.div
                          initial="hidden"
                          animate="visible"
                          variants={{ visible: { transition: { staggerChildren: 0.07 } } }}
                          style={{ marginTop: 10 }}
                        >
                          <div style={s.actionsTitle}>RECOMMENDED ACTIONS</div>
                          {report.recommended_actions.map((action, i) => (
                            <motion.div
                              key={i}
                              variants={{ hidden: { x: -12, opacity: 0 }, visible: { x: 0, opacity: 1 } }}
                              style={s.actionItem}
                            >
                              <span style={{ color: "#00D4FF", marginRight: 6 }}>→</span>
                              {action}
                            </motion.div>
                          ))}
                        </motion.div>
                      )}
                    </motion.div>
                  ) : !loading ? (
                    <motion.p
                      key="hint"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      style={s.hintText}
                    >
                      Click "Run AI Analysis" to generate a Gemini-powered forensic report.
                    </motion.p>
                  ) : null}
                </AnimatePresence>
              </motion.div>
            </motion.div>
          </div>

          {/* ── Shield Button (sticky footer) ── */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.55, type: "spring", stiffness: 220, damping: 22 }}
            style={s.shieldSection}
          >
            <motion.button
              onClick={handleShield}
              disabled={txStatus === "pending"}
              whileHover={{ scale: txStatus === "pending" ? 1 : 1.02, boxShadow: "0 0 24px rgba(255,59,59,0.35)" }}
              whileTap={{ scale: 0.97 }}
              style={{
                ...s.shieldBtn,
                opacity: txStatus === "pending" ? 0.6 : 1,
                cursor: txStatus === "pending" ? "wait" : "pointer",
                ...(txStatus === "success" ? { borderColor: "#4ADE80", color: "#4ADE80", background: "rgba(74,222,128,0.08)" } : {}),
                ...(txStatus === "error"   ? { borderColor: "#FF3B3B", color: "#FF3B3B" } : {}),
              }}
            >
              {txStatus === "pending" && "⏳ Confirming on Base Sepolia…"}
              {txStatus === "success" && "✅ Shield Active — Blacklisted On-Chain"}
              {txStatus === "error"   && "❌ Failed — Check console & retry"}
              {txStatus === "idle"    && "🛡 Activate Guardian Shield"}
            </motion.button>

            <AnimatePresence>
              {txHash && (
                <motion.a
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  href={`https://sepolia.basescan.org/tx/${txHash}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={s.txLink}
                >
                  View on BaseScan ↗ {txHash.slice(0, 10)}…{txHash.slice(-6)}
                </motion.a>
              )}
            </AnimatePresence>

            {/* Close button */}
            <motion.button
              onClick={onClose}
              whileHover={{ background: "rgba(255,255,255,0.08)" }}
              style={s.closeBtn}
            >
              ✕ Close Panel
            </motion.button>
          </motion.div>
        </motion.aside>
      )}
    </AnimatePresence>

    {/* ── Expanded Graph Modal ── */}
    <AnimatePresence>
      {expandedGraph && (
        <motion.div
          key="graph-modal"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => setExpandedGraph(false)}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 200,
            background: "rgba(0,0,0,0.82)",
            backdropFilter: "blur(10px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "40px 32px",
          }}
        >
          <motion.div
            initial={{ scale: 0.88, opacity: 0, y: 24 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.92, opacity: 0, y: 16 }}
            transition={{ type: "spring", stiffness: 280, damping: 26 }}
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(900px, 90vw)",
              background: "rgba(2, 6, 23, 0.97)",
              border: "1px solid rgba(239,68,68,0.4)",
              borderRadius: 16,
              boxShadow: "0 0 60px rgba(239,68,68,0.12), 0 24px 80px rgba(0,0,0,0.9)",
              overflow: "hidden",
              fontFamily: "'Inter', sans-serif",
            }}
          >
            {/* Modal Header */}
            <div style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "16px 24px 12px",
              borderBottom: "1px solid rgba(239,68,68,0.15)",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ position: "relative", display: "inline-flex" }}>
                  <span style={{
                    position: "absolute",
                    width: 10, height: 10,
                    borderRadius: "50%",
                    background: "#ef4444",
                    opacity: 0.5,
                    animation: "ping 1.5s cubic-bezier(0,0,0.2,1) infinite",
                  }} />
                  <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#ef4444", display: "inline-block", boxShadow: "0 0 8px #ef4444" }} />
                </span>
                <span style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 13,
                  fontWeight: 700,
                  letterSpacing: "0.14em",
                  color: "#ef4444",
                }}>THREAT ACTIVITY — EXPANDED VIEW</span>
                <span style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 10,
                  color: "#475569",
                  marginLeft: 8,
                }}>ROLLING · 1H WINDOW</span>
              </div>
              <button
                onClick={() => setExpandedGraph(false)}
                style={{
                  background: "rgba(239,68,68,0.08)",
                  border: "1px solid rgba(239,68,68,0.3)",
                  borderRadius: 6,
                  color: "#ef4444",
                  cursor: "pointer",
                  padding: "4px 12px",
                  fontSize: 12,
                  fontFamily: "'JetBrains Mono', monospace",
                  letterSpacing: "0.08em",
                }}
              >
                ✕ CLOSE
              </button>
            </div>

            {/* Chart — full size */}
            <div style={{ padding: "8px 0 8px" }}>
              <ThreatActivityGraph height={380} />
            </div>

            {/* Footer hint */}
            <div style={{
              padding: "8px 24px 14px",
              borderTop: "1px solid rgba(239,68,68,0.1)",
              fontSize: 10,
              color: "#475569",
              fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: "0.08em",
            }}>
              ESC or click outside to dismiss  ·  hover over the chart for exact values
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
    </>
  );
}

// ── Styles ─────────────────────────────────────────────────────
const s: Record<string, React.CSSProperties> = {
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 18,
    gap: 12,
  },
  riskBadge: {
    display: "inline-block",
    padding: "4px 12px",
    borderRadius: 6,
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: "0.08em",
  },
  exploitTag: {
    background: "rgba(255,59,59,0.15)",
    border: "1px solid #FF3B3B",
    borderRadius: 4,
    padding: "2px 8px",
    fontSize: 10,
    fontWeight: 800,
    color: "#FF3B3B",
    letterSpacing: "0.12em",
  },
  walletAddr: {
    fontSize: 14,
    fontFamily: "'JetBrains Mono', monospace",
    color: "#CBD5E1",
    margin: "4px 0",
    letterSpacing: "0.02em",
  },
  labelBadge: { fontSize: 11, color: "#64748B", letterSpacing: "0.1em" },
  statsRow: {
    display: "flex",
    gap: 10,
    marginBottom: 18,
  },
  statCard: {
    flex: 1,
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 10,
    padding: "10px 12px",
    textAlign: "center" as const,
  },
  statValue: { fontSize: 15, fontWeight: 700, color: "#E2E8F0", marginBottom: 3 },
  statLabel: { fontSize: 10, color: "#64748B", letterSpacing: "0.07em" },
  catSection: {
    background: "rgba(255,59,59,0.05)",
    border: "1px solid rgba(255,59,59,0.2)",
    borderRadius: 10,
    padding: "12px 14px",
    marginBottom: 16,
  },
  catTag: {
    background: "rgba(255,59,59,0.12)",
    border: "1px solid rgba(255,59,59,0.3)",
    borderRadius: 4,
    padding: "4px 10px",
    fontSize: 11,
    color: "#FF8C8C",
    fontWeight: 600,
    letterSpacing: "0.05em",
  },
  section: { marginBottom: 10 },
  sectionLabel: {
    fontSize: 11,
    fontWeight: 700,
    color: "#FF3B3B",
    letterSpacing: "0.1em",
  },
  sectionHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 14,
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: "0.1em",
    color: "#00D4FF",
  },
  analyzeBtn: {
    background: "rgba(0,212,255,0.08)",
    border: "1px solid rgba(0,212,255,0.35)",
    borderRadius: 6,
    color: "#00D4FF",
    cursor: "pointer",
    padding: "6px 14px",
    fontSize: 12,
    fontWeight: 600,
    fontFamily: "'Inter', sans-serif",
  },
  errorBox: {
    background: "rgba(255,59,59,0.1)",
    border: "1px solid rgba(255,59,59,0.3)",
    borderRadius: 6,
    padding: "10px 14px",
    fontSize: 13,
    color: "#FF3B3B",
    marginBottom: 10,
  },
  riskBanner: {
    border: "1px solid",
    borderRadius: 6,
    padding: "7px 14px",
    fontSize: 13,
    fontWeight: 700,
    letterSpacing: "0.08em",
    marginBottom: 12,
    overflow: "hidden",
  },
  summaryText: { fontSize: 14, color: "#CBD5E1", lineHeight: 1.7, marginBottom: 12 },
  narrativeBox: {
    background: "rgba(255,255,255,0.02)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 10,
    padding: 14,
    marginBottom: 12,
    maxHeight: 180,
    overflowY: "auto" as const,
  },
  narrativeText: { fontSize: 13, color: "#94A3B8", lineHeight: 1.8, margin: 0 },
  actionsTitle: { fontSize: 11, fontWeight: 700, color: "#64748B", letterSpacing: "0.1em", marginBottom: 10 },
  actionItem: { fontSize: 13, color: "#94A3B8", padding: "5px 0", lineHeight: 1.6 },
  hintText: { fontSize: 13, color: "#475569", lineHeight: 1.65, margin: 0 },
  shieldSection: {
    padding: "14px 18px 18px",
    borderTop: "1px solid rgba(255,59,59,0.15)",
    display: "flex",
    flexDirection: "column" as const,
    gap: 8,
    background: "rgba(0,0,0,0.25)",
  },
  shieldBtn: {
    background: "linear-gradient(135deg, rgba(255,59,59,0.12), rgba(255,140,0,0.08))",
    border: "1px solid #FF3B3B",
    borderRadius: 8,
    color: "#FF3B3B",
    padding: "12px 16px",
    fontSize: 13,
    fontWeight: 700,
    letterSpacing: "0.05em",
    width: "100%",
    fontFamily: "'Inter', sans-serif",
  },
  txLink: { fontSize: 11, color: "#00D4FF", textDecoration: "none", textAlign: "center" as const },
  closeBtn: {
    background: "transparent",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 6,
    color: "#64748B",
    cursor: "pointer",
    padding: "7px",
    fontSize: 12,
    width: "100%",
    fontFamily: "'Inter', sans-serif",
    transition: "background 0.2s",
  },
};
