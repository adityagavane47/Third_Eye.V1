/**
 * Dashboard.tsx — Main Layout
 */

import { useCallback, useEffect, useState } from "react";
import Galaxy3D, { type GalaxyNode, type GraphData } from "../components/Galaxy3D";
import Sidebar from "../components/Sidebar";
import { useAuth } from "../context/AuthContext";

// Relative paths handled by Vite proxy
const API_BASE = "";


const EMPTY_GRAPH: GraphData = { nodes: [], links: [] };

export default function Dashboard() {
  const { authenticated, walletAddress, login, logout } = useAuth();



  const [graphData, setGraphData] = useState<GraphData>(EMPTY_GRAPH);
  const [selectedNode, setSelectedNode] = useState<GalaxyNode | null>(null);
  const [alertMode, setAlertMode] = useState(false);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [simulating, setSimulating] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" | "info" } | null>(null);

  const showToast = (msg: string, type: "success" | "error" | "info" = "info") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4500);
  };


  const fetchGraph = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/graph/nodes?limit=200`);
      if (!res.ok) throw new Error("Graph fetch failed");
      const data = await res.json();
      setGraphData(data);
      setAlertMode(data.nodes?.some((n: GalaxyNode) => n.flagged) ?? false);
      setLastRefresh(new Date());
    } catch {

      setGraphData(MOCK_GRAPH_DATA);
      setAlertMode(MOCK_GRAPH_DATA.nodes.some((n) => n.flagged));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGraph();
    const interval = setInterval(fetchGraph, 30_000);
    return () => clearInterval(interval);
  }, [fetchGraph]);

  const handleNodeSelect = (node: GalaxyNode) => {
    setSelectedNode(node);
  };


  const handleOpenPanel = () => {
    if (!selectedNode && graphData.nodes.length > 0) {
      const riskiest = [...graphData.nodes].sort((a, b) => b.riskScore - a.riskScore)[0];
      setSelectedNode(riskiest);
    }
  };

  const handleSidebarClose = () => {
    setSelectedNode(null);
  };

  const simulateExploit = async () => {

    if (!authenticated) {
      showToast("Connect your wallet first to activate the on-chain shield.", "error");
      login();
      return;
    }

    setSimulating(true);
    showToast("🚨 Injecting exploit wallet into the galaxy…", "info");

    // Show placeholder sidebar immediately
    const placeholderNode: GalaxyNode = {
      id: "simulating",
      address: "0xDetecting…",
      label: "attacker",
      riskScore: 0.98,
      flagged: true,
      txCount: 0,
      balanceEth: 0,
    };
    setSelectedNode(placeholderNode);
    setAlertMode(true);

    try {
      // Inject attacker
      const res = await fetch("/api/simulate-exploit", { method: "POST" });
      if (!res.ok) throw new Error(`Backend HTTP ${res.status}`);
      const data = await res.json();

      const attackerAddress: string = data.attacker_address;
      const mlRiskScore: number    = data.ml_score ?? 0.98;

      // Update sidebar with real attacker
      const attackerNode: GalaxyNode = {
        id:         attackerAddress,
        address:    attackerAddress,
        label:      "attacker",
        riskScore:  mlRiskScore,
        flagged:    true,
        txCount:    150,
        balanceEth: 5.0,
      };
      setSelectedNode(attackerNode);

      // Shield blacklist on Base Sepolia
      showToast("⏳ Confirming on Base Sepolia…", "info");
      const shieldRes = await fetch("/api/shield/blacklist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          wallet_address: attackerAddress,
          risk_score:     mlRiskScore,
          reason:         "Automated detection: Simulated exploit pattern — ML + PSI confirmed",
        }),
      });
      const shieldData = await shieldRes.json();

      // Handle on-chain result
      if (shieldRes.ok && shieldData.tx_hash) {
        const h = shieldData.tx_hash as string;
        showToast(
          `✅ Shield Activated — Blacklisted on Base Sepolia\nTx: ${h.slice(0, 12)}…${h.slice(-6)}`,
          "success",
        );
      } else {
        const detail = shieldData.detail ?? "Unknown error";
        const isOperator = detail.toLowerCase().includes("operator") ||
                           detail.toLowerCase().includes("access");
        showToast(
          isOperator
            ? "Missing Operator Role — wallet not granted on ThirdEyeGuardian.sol"
            : `Shield tx failed: ${detail}`,
          "error",
        );
      }


      fetchGraph();

    } catch (err: any) {
      showToast(`Backend: ${err?.message ?? "fetch failed"} — demo mode`, "error");
    } finally {
      setSimulating(false);
    }
  };


  return (
    <div style={styles.root}>
      {/* Top Navigation Bar */}
      <nav style={styles.nav}>
        <div style={styles.navBrand}>
          <span style={styles.navLogo}>🛡</span>
          <span style={styles.navTitle}>Third Eye</span>
          {alertMode && (
            <span style={styles.alertPill}>⚠ THREATS ACTIVE</span>
          )}
        </div>

        <div style={styles.navStats}>
          <span style={styles.statChip}>
            ⬡ {graphData.nodes.length.toLocaleString()} Nodes
          </span>
          <span style={styles.statChip}>
            🔗 {graphData.links.length.toLocaleString()} Edges
          </span>
          <span style={{ ...styles.statChip, color: "#FF3B3B" }}>
            🚨 {graphData.nodes.filter((n) => n.flagged).length} Flagged
          </span>
          {lastRefresh && (
            <span style={{ ...styles.statChip, color: "#64748B" }}>
              ↻ {lastRefresh.toLocaleTimeString()}
            </span>
          )}
        </div>

        <div style={styles.navActions}>
          <button onClick={fetchGraph} style={styles.refreshBtn}>⟳ Refresh</button>
          <button onClick={handleOpenPanel} style={styles.refreshBtn}>🔍 Inspect Node</button>
          <button
            onClick={simulateExploit}
            disabled={simulating}
            style={{ ...styles.exploitBtn, opacity: simulating ? 0.6 : 1 }}
          >
            {simulating ? "⏳ Injecting…" : "💀 Simulate Exploit"}
          </button>
          {authenticated ? (
            <div style={styles.walletGroup}>
              <div style={styles.walletAddress}>
                <span style={styles.walletDot} />
                {walletAddress ?? "Connected"}
              </div>
              <button onClick={() => logout()} style={styles.logoutBtn}>Disconnect</button>
            </div>
          ) : (
            <button onClick={() => login()} style={styles.connectBtn}>Connect Wallet</button>
          )}
        </div>
      </nav>

      {/* Toast Notification */}
      {toast && (
        <div style={{
          ...styles.toast,
          background:
            toast.type === "success" ? "rgba(74,222,128,0.12)" :
            toast.type === "error"   ? "rgba(255,59,59,0.12)"  :
                                       "rgba(0,212,255,0.10)",
          borderColor:
            toast.type === "success" ? "#4ADE80" :
            toast.type === "error"   ? "#FF3B3B"  :
                                       "#00D4FF",
          color:
            toast.type === "success" ? "#4ADE80" :
            toast.type === "error"   ? "#FF3B3B"  :
                                       "#00D4FF",
        }}>
          {toast.msg}
        </div>
      )}

      {/* Main Content Area */}
      <div style={styles.content}>
        {/* 3D Galaxy — always fills the full area */}
        <div style={{ width: "100%", height: "100%", position: "relative" }}>
          {loading ? (
            <div style={styles.loadingScreen}>
              <div style={styles.loadingSpinner} />
              <p style={styles.loadingText}>Initializing Third Eye…</p>
            </div>
          ) : (
            <Galaxy3D
              graphData={graphData}
              onNodeSelect={handleNodeSelect}
              selectedNode={selectedNode}
              alertMode={alertMode}
            />
          )}
        </div>

        {/* Sidebar — Framer Motion AnimatePresence handles open/close */}
        <Sidebar
          selectedNode={selectedNode}
          onClose={handleSidebarClose}
          isExploitDetected={alertMode}
        />
      </div>

      {/* CSS Animations */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #000; overflow: hidden; }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
      `}</style>
    </div>
  );
}


const styles: Record<string, React.CSSProperties> = {
  root: {
    width: "100vw",
    height: "100vh",
    display: "flex",
    flexDirection: "column",
    background: "#000008",
    overflow: "hidden",
    fontFamily: "'Inter', sans-serif",
  },
  nav: {
    height: 56,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "0 20px",
    background: "rgba(6, 6, 15, 0.95)",
    borderBottom: "1px solid rgba(0, 212, 255, 0.15)",
    backdropFilter: "blur(12px)",
    zIndex: 100,
    gap: 16,
  },
  navBrand: { display: "flex", alignItems: "center", gap: 10 },
  navLogo: { fontSize: 22 },
  navTitle: {
    fontSize: 15,
    fontWeight: 800,
    letterSpacing: "0.18em",
    color: "#00D4FF",
    fontFamily: "'JetBrains Mono', monospace",
  },
  alertPill: {
    background: "rgba(255,59,59,0.15)",
    border: "1px solid #FF3B3B",
    borderRadius: 6,
    padding: "2px 8px",
    fontSize: 10,
    fontWeight: 700,
    color: "#FF3B3B",
    letterSpacing: "0.08em",
    animation: "pulse 1.5s ease-in-out infinite",
  },
  navStats: { display: "flex", gap: 8, flex: 1, justifyContent: "center" },
  statChip: {
    background: "rgba(255,255,255,0.04)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 6,
    padding: "3px 10px",
    fontSize: 11,
    color: "#94A3B8",
    fontFamily: "'JetBrains Mono', monospace",
  },
  navActions: { display: "flex", alignItems: "center", gap: 10 },
  refreshBtn: {
    background: "transparent",
    border: "1px solid rgba(0,212,255,0.3)",
    borderRadius: 6,
    color: "#00D4FF",
    cursor: "pointer",
    padding: "5px 12px",
    fontSize: 12,
  },
  exploitBtn: {
    background: "linear-gradient(135deg, rgba(255,59,59,0.15), rgba(255,140,0,0.10))",
    border: "1px solid #FF3B3B",
    borderRadius: 8,
    color: "#FF3B3B",
    cursor: "pointer",
    padding: "6px 14px",
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: "0.04em",
    transition: "all 0.2s",
  },
  toast: {
    position: "fixed" as const,
    bottom: 28,
    left: "50%",
    transform: "translateX(-50%)",
    border: "1px solid",
    borderRadius: 10,
    padding: "12px 24px",
    fontSize: 13,
    fontWeight: 600,
    fontFamily: "'Inter', sans-serif",
    backdropFilter: "blur(12px)",
    zIndex: 9999,
    pointerEvents: "none" as const,
    letterSpacing: "0.02em",
    boxShadow: "0 4px 24px rgba(0,0,0,0.4)",
  },
  connectBtn: {
    background: "linear-gradient(135deg, #4F46E5, #7C3AED)",
    border: "none",
    borderRadius: 8,
    color: "#fff",
    cursor: "pointer",
    padding: "7px 16px",
    fontSize: 12,
    fontWeight: 700,
  },
  walletGroup: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    background: "rgba(0,212,255,0.06)",
    border: "1px solid rgba(0,212,255,0.25)",
    borderRadius: 8,
    padding: "4px 4px 4px 12px",
  },
  walletAddress: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    fontSize: 11,
    fontFamily: "'JetBrains Mono', monospace",
    color: "#00D4FF",
    letterSpacing: "0.04em",
  },
  walletDot: {
    width: 6,
    height: 6,
    borderRadius: "50%",
    background: "#4ADE80",
    boxShadow: "0 0 6px #4ADE80",
    display: "inline-block" as const,
  },
  logoutBtn: {
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 6,
    color: "#94A3B8",
    cursor: "pointer",
    padding: "4px 10px",
    fontSize: 11,
  },
  content: {
    flex: 1,
    display: "flex",
    overflow: "hidden",
    position: "relative",  // needed for absolute sidebar overlay
  },
  loadingScreen: {
    position: "absolute",
    inset: 0,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 20,
    background: "#000008",
  },
  loadingSpinner: {
    width: 48,
    height: 48,
    border: "3px solid rgba(0,212,255,0.15)",
    borderTop: "3px solid #00D4FF",
    borderRadius: "50%",
    animation: "spin 1s linear infinite",
  },
  loadingText: {
    color: "#00D4FF",
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: 13,
    letterSpacing: "0.1em",
  },
};

// ── Mock data (dev fallback when backend is offline) ───────────
const MOCK_GRAPH_DATA: GraphData = {
  nodes: Array.from({ length: 80 }, (_, i) => ({
    id: `0x${i.toString(16).padStart(40, "0")}`,
    address: `0x${i.toString(16).padStart(40, "0")}`,
    label: (["defi_user", "bot", "whale", "exchange"] as const)[i % 4], // Removed "attacker" to maintain initial peace state
    riskScore: 0, // Default to safe value (0) instead of random
    flagged: false, // Default to safe value (false) instead of random
    txCount: Math.floor(Math.random() * 5000),
    balanceEth: Math.random() * 100,
  })),
  links: Array.from({ length: 120 }, (_, i) => ({
    source: `0x${(i % 80).toString(16).padStart(40, "0")}`,
    target: `0x${((i + 7) % 80).toString(16).padStart(40, "0")}`,
    txHash: `0x${"a".repeat(64)}`,
    valueEth: Math.random() * 20,
  })),
};
