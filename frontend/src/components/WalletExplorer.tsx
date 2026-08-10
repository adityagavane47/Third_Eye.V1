/**
 * WalletExplorer.tsx — Wallet Relationship Explorer
 * Opens as a full-screen modal overlay showing 1-2 hop neighbors
 * of the selected wallet with directed transaction flow edges.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { AnimatePresence, motion } from "framer-motion";
import type { GalaxyNode, GalaxyLink } from "./Galaxy3D";

// ── Types ──────────────────────────────────────────────────────
interface ExplorerNode extends GalaxyNode {
  hopDepth?: number;
  isOrigin?: boolean;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number;
  fy?: number;
}

interface ExplorerLink extends Omit<GalaxyLink, "source" | "target"> {
  source: string | ExplorerNode;
  target: string | ExplorerNode;
}

interface NeighborStats {
  totalNodes: number;
  totalEdges: number;
  totalVolumeEth: number;
  flaggedNeighbors: number;
  directNeighbors: number;
}

interface NeighborData {
  origin: string;
  nodes: ExplorerNode[];
  links: ExplorerLink[];
  stats: NeighborStats;
}

interface WalletExplorerProps {
  isOpen: boolean;
  originNode: GalaxyNode | null;
  fallbackGraph: { nodes: GalaxyNode[]; links: GalaxyLink[] };
  onClose: () => void;
  onNodeSelect: (node: GalaxyNode) => void;
}

// ── Colour helpers ─────────────────────────────────────────────
function riskColor(riskScore: number, flagged: boolean): string {
  if (flagged || riskScore > 0.85) return "#FF3B3B";
  if (riskScore > 0.65) return "#FF8C00";
  if (riskScore > 0.40) return "#FFD700";
  if (riskScore > 0.20) return "#00D4FF";
  return "#4ADE80";
}

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

function nodeSize(node: ExplorerNode): number {
  if (node.isOrigin) return 10;
  const base = node.label === "whale" ? 7 : node.label === "exchange" ? 6 : 4;
  return base + node.riskScore * 3;
}

// ── Build mock sub-graph from existing graphData ───────────────
function buildMockNeighborData(
  originNode: GalaxyNode,
  fallbackGraph: { nodes: GalaxyNode[]; links: GalaxyLink[] }
): NeighborData {
  const originAddr = originNode.address;
  const getAddr = (s: string | GalaxyNode): string =>
    typeof s === "string" ? s : s.address;

  const directLinks = fallbackGraph.links.filter(
    (l) => getAddr(l.source) === originAddr || getAddr(l.target) === originAddr
  );

  const directAddresses = new Set<string>([originAddr]);
  directLinks.forEach((l) => {
    directAddresses.add(getAddr(l.source));
    directAddresses.add(getAddr(l.target));
  });

  const secondLinks = fallbackGraph.links.filter((l) => {
    const src = getAddr(l.source);
    const tgt = getAddr(l.target);
    return (directAddresses.has(src) || directAddresses.has(tgt)) && src !== originAddr && tgt !== originAddr;
  });

  const allAddresses = new Set(directAddresses);
  secondLinks.forEach((l) => {
    allAddresses.add(getAddr(l.source));
    allAddresses.add(getAddr(l.target));
  });

  const limitedAddresses = [...allAddresses].slice(0, 60);
  const addrSet = new Set(limitedAddresses);

  const nodesOut: ExplorerNode[] = fallbackGraph.nodes
    .filter((n) => addrSet.has(n.address))
    .map((n) => ({
      ...n,
      hopDepth: n.address === originAddr ? 0 : directAddresses.has(n.address) ? 1 : 2,
      isOrigin: n.address === originAddr,
    }));

  const linksOut: ExplorerLink[] = [...directLinks, ...secondLinks]
    .filter((l) => {
      const src = getAddr(l.source);
      const tgt = getAddr(l.target);
      return addrSet.has(src) && addrSet.has(tgt);
    })
    .map((l) => ({
      ...l,
      source: getAddr(l.source),
      target: getAddr(l.target),
    })) as ExplorerLink[];

  const totalVol = linksOut.reduce((acc, l) => acc + (l.valueEth ?? 0), 0);
  const flaggedCount = nodesOut.filter((n) => n.flagged && !n.isOrigin).length;

  return {
    origin: originAddr,
    nodes: nodesOut,
    links: linksOut,
    stats: {
      totalNodes: nodesOut.length,
      totalEdges: linksOut.length,
      totalVolumeEth: Math.round(totalVol * 10000) / 10000,
      flaggedNeighbors: flaggedCount,
      directNeighbors: nodesOut.filter((n) => n.hopDepth === 1).length,
    },
  };
}

// ── Stat Chip ─────────────────────────────────────────────────
function StatChip({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.04)",
      border: `1px solid ${color ? hexToRgba(color, 0.3) : "rgba(255,255,255,0.08)"}`,
      borderRadius: 8,
      padding: "8px 14px",
      textAlign: "center",
      minWidth: 80,
    }}>
      <div style={{ fontSize: 16, fontWeight: 800, color: color ?? "#E2E8F0", fontFamily: "'JetBrains Mono', monospace" }}>
        {value}
      </div>
      <div style={{ fontSize: 9, color: "#64748B", letterSpacing: "0.08em", marginTop: 2, textTransform: "uppercase" as const }}>
        {label}
      </div>
    </div>
  );
}

// ── Loading skeleton ───────────────────────────────────────────
function LoadingSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 20 }}>
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 1.4, repeat: Infinity, ease: "linear" }}
        style={{ width: 48, height: 48, border: "3px solid rgba(0,212,255,0.12)", borderTop: "3px solid #00D4FF", borderRadius: "50%" }}
      />
      <div style={{ color: "#00D4FF", fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: "0.12em" }}>
        MAPPING WALLET NETWORK...
      </div>
      <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
        {[40, 60, 30, 50, 35].map((size, i) => (
          <motion.div
            key={i}
            animate={{ opacity: [0.2, 0.6, 0.2] }}
            transition={{ duration: 1.5, repeat: Infinity, delay: i * 0.2 }}
            style={{ width: size, height: size, borderRadius: "50%", background: "rgba(0,212,255,0.15)", border: "1px solid rgba(0,212,255,0.25)" }}
          />
        ))}
      </div>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────
export default function WalletExplorer({
  isOpen,
  originNode,
  fallbackGraph,
  onClose,
  onNodeSelect,
}: WalletExplorerProps) {
  const [data, setData] = useState<NeighborData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<ExplorerNode | null>(null);
  const [selectedPath, setSelectedPath] = useState<Set<string>>(new Set());
  const [pathStart, setPathStart] = useState<ExplorerNode | null>(null);
  const [pathMode, setPathMode] = useState(false);
  const graphRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });

  useEffect(() => {
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({ width: entry.contentRect.width, height: entry.contentRect.height });
      }
    });
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!isOpen || !originNode) return;
    setData(null);
    setError(null);
    setPathStart(null);
    setSelectedPath(new Set());

    const fetchNeighbors = async () => {
      setLoading(true);
      try {
        const res = await fetch(`/api/graph/neighbors/${originNode.address}?hops=2&limit=120`);
        if (!res.ok) throw new Error(`API ${res.status}`);
        const json = await res.json();
        setData(json);
      } catch {
        const mock = buildMockNeighborData(originNode, fallbackGraph);
        setData(mock);
        setError("Backend offline - showing local sub-graph");
      } finally {
        setLoading(false);
      }
    };
    fetchNeighbors();
  }, [isOpen, originNode, fallbackGraph]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (isOpen) window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  const tracePath = useCallback((from: ExplorerNode, to: ExplorerNode, links: ExplorerLink[]) => {
    const adj = new Map<string, string[]>();
    links.forEach((l) => {
      const src = typeof l.source === "string" ? l.source : (l.source as ExplorerNode).address;
      const tgt = typeof l.target === "string" ? l.target : (l.target as ExplorerNode).address;
      if (!adj.has(src)) adj.set(src, []);
      if (!adj.has(tgt)) adj.set(tgt, []);
      adj.get(src)!.push(tgt);
      adj.get(tgt)!.push(src);
    });
    const queue: string[][] = [[from.address]];
    const visited = new Set<string>();
    while (queue.length) {
      const path = queue.shift()!;
      const node = path[path.length - 1];
      if (node === to.address) return new Set(path);
      if (visited.has(node)) continue;
      visited.add(node);
      (adj.get(node) ?? []).forEach((nb) => queue.push([...path, nb]));
    }
    return new Set<string>();
  }, []);

  const handleNodeClick = useCallback((node: ExplorerNode) => {
    if (pathMode) {
      if (!pathStart) {
        setPathStart(node);
        setSelectedPath(new Set([node.address]));
      } else {
        if (data?.links) {
          const path = tracePath(pathStart, node, data.links);
          setSelectedPath(path);
        }
        setPathStart(null);
      }
      return;
    }
    onNodeSelect(node);
  }, [pathMode, pathStart, data, tracePath, onNodeSelect]);

  const paintNode = useCallback((node: ExplorerNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
    // Guard: x/y are undefined during warm-up ticks before layout is computed
    if (node.x === undefined || node.y === undefined) return;

    const addr = node.address;
    const color = riskColor(node.riskScore, node.flagged);
    const size = nodeSize(node);
    const isHighlighted = selectedPath.has(addr);
    const isPathStart = pathStart?.address === addr;
    const isHovered = hoveredNode?.address === addr;

    if (node.isOrigin || node.flagged || isHighlighted || isHovered) {
      const glowSize = size * (node.isOrigin ? 3.5 : 2.4);
      const gradient = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, glowSize);
      gradient.addColorStop(0, hexToRgba(color, node.isOrigin ? 0.25 : 0.15));
      gradient.addColorStop(1, "rgba(0,0,0,0)");
      ctx.beginPath();
      ctx.arc(node.x, node.y, glowSize, 0, Math.PI * 2);
      ctx.fillStyle = gradient;
      ctx.fill();
    }

    if ((node.hopDepth ?? 0) === 2) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, size + 3, 0, Math.PI * 2);
      ctx.strokeStyle = hexToRgba(color, 0.3);
      ctx.setLineDash([2, 3]);
      ctx.lineWidth = 0.8 / globalScale;
      ctx.stroke();
      ctx.setLineDash([]);
    }

    ctx.beginPath();
    ctx.arc(node.x, node.y, size, 0, Math.PI * 2);
    ctx.fillStyle = isPathStart ? "#FFFFFF" : color;
    ctx.fill();
    ctx.strokeStyle = isHighlighted ? "#FFFFFF" : node.isOrigin ? "#FFFFFF" : hexToRgba(color, 0.7);
    ctx.lineWidth = node.isOrigin ? 2 / globalScale : 1 / globalScale;
    ctx.stroke();

    if (globalScale > 1.2 || node.isOrigin || isHovered) {
      const label = `${addr.slice(0, 6)}...${addr.slice(-4)}`;
      ctx.font = `${node.isOrigin ? 11 : 9}px 'JetBrains Mono', monospace`;
      ctx.fillStyle = isHovered || node.isOrigin ? "#FFFFFF" : hexToRgba(color, 0.9);
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillText(label, node.x, node.y + size + 2);
    }
  }, [hoveredNode, selectedPath, pathStart]);


  const paintLink = useCallback((link: ExplorerLink, ctx: CanvasRenderingContext2D) => {
    const src = link.source as ExplorerNode;
    const tgt = link.target as ExplorerNode;
    if (!src?.x || !tgt?.x || !src?.y || !tgt?.y) return;
    const isHighlighted = selectedPath.has(src.address) && selectedPath.has(tgt.address);
    const alpha = isHighlighted ? 0.9 : 0.25;
    const lineWidth = Math.max(0.5, Math.min(3, 0.5 + (link.valueEth ?? 0) * 0.15));
    const color = (link.valueEth ?? 0) > 10 ? "#FF3B3B" : (link.valueEth ?? 0) > 1 ? "#FF8C00" : "#00D4FF";
    ctx.beginPath();
    ctx.moveTo(src.x!, src.y!);
    ctx.lineTo(tgt.x!, tgt.y!);
    ctx.strokeStyle = hexToRgba(color, alpha);
    ctx.lineWidth = lineWidth;
    ctx.stroke();
    const dx = tgt.x! - src.x!;
    const dy = tgt.y! - src.y!;
    const len = Math.sqrt(dx * dx + dy * dy);
    if (len < 1) return;
    const ux = dx / len;
    const uy = dy / len;
    const tSize = nodeSize(tgt);
    const ax = tgt.x! - ux * (tSize + 2);
    const ay = tgt.y! - uy * (tSize + 2);
    const arrowLen = 6;
    const arrowAngle = 0.45;
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    ctx.lineTo(ax - arrowLen * Math.cos(Math.atan2(dy, dx) - arrowAngle), ay - arrowLen * Math.sin(Math.atan2(dy, dx) - arrowAngle));
    ctx.lineTo(ax - arrowLen * Math.cos(Math.atan2(dy, dx) + arrowAngle), ay - arrowLen * Math.sin(Math.atan2(dy, dx) + arrowAngle));
    ctx.closePath();
    ctx.fillStyle = hexToRgba(color, alpha);
    ctx.fill();
  }, [selectedPath]);

  const graphData = data ? { nodes: data.nodes as any[], links: data.links as any[] } : { nodes: [], links: [] };
  const stats = data?.stats;

  return (
    <AnimatePresence>
      {isOpen && originNode && (
        <motion.div
          key="wallet-explorer"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          onClick={onClose}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 300,
            background: "rgba(0,0,4,0.85)",
            backdropFilter: "blur(16px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "24px",
            fontFamily: "'Inter', sans-serif",
          }}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0, y: 32 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.93, opacity: 0, y: 16 }}
            transition={{ type: "spring", stiffness: 300, damping: 28 }}
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(1100px, 96vw)",
              height: "min(780px, 90vh)",
              display: "flex",
              flexDirection: "column",
              background: "rgba(2, 6, 23, 0.97)",
              border: "1px solid rgba(0,212,255,0.2)",
              borderRadius: 20,
              boxShadow: "0 0 80px rgba(0,212,255,0.08), 0 32px 100px rgba(0,0,0,0.95)",
              overflow: "hidden",
            }}
          >
            <div style={{ height: 2, background: "linear-gradient(90deg, transparent, #00D4FF 40%, #7C3AED 60%, transparent)" }} />

            {/* Header */}
            <div style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "14px 20px",
              borderBottom: "1px solid rgba(0,212,255,0.12)",
              gap: 12,
              flexShrink: 0,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{
                  background: `${riskColor(originNode.riskScore, originNode.flagged)}18`,
                  border: `1px solid ${riskColor(originNode.riskScore, originNode.flagged)}55`,
                  borderRadius: 8,
                  padding: "5px 12px",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}>
                  <motion.div
                    animate={{ scale: [1, 1.5, 1], opacity: [0.8, 0.2, 0.8] }}
                    transition={{ duration: 1.6, repeat: Infinity }}
                    style={{ width: 7, height: 7, borderRadius: "50%", background: riskColor(originNode.riskScore, originNode.flagged) }}
                  />
                  <span style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: 12,
                    color: riskColor(originNode.riskScore, originNode.flagged),
                    fontWeight: 700,
                    letterSpacing: "0.05em",
                  }}>
                    {originNode.address.slice(0, 10)}...{originNode.address.slice(-6)}
                  </span>
                </div>
                <span style={{ color: "#475569", fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}>
                  NETWORK EXPLORER  1-2 HOP RADIUS
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <motion.button
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => { setPathMode((p) => !p); setPathStart(null); setSelectedPath(new Set()); }}
                  style={{
                    background: pathMode ? "rgba(124,58,237,0.2)" : "rgba(255,255,255,0.04)",
                    border: `1px solid ${pathMode ? "#7C3AED" : "rgba(255,255,255,0.1)"}`,
                    borderRadius: 6,
                    color: pathMode ? "#A78BFA" : "#64748B",
                    cursor: "pointer",
                    padding: "5px 12px",
                    fontSize: 11,
                    fontFamily: "'JetBrains Mono', monospace",
                    letterSpacing: "0.06em",
                    transition: "all 0.2s",
                  }}
                >
                  {pathMode ? (pathStart ? "PICK END" : "PICK START") : "PATH TRACE"}
                </motion.button>
                <motion.button
                  whileHover={{ background: "rgba(255,59,59,0.12)" }}
                  whileTap={{ scale: 0.96 }}
                  onClick={onClose}
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: 6,
                    color: "#64748B",
                    cursor: "pointer",
                    padding: "5px 12px",
                    fontSize: 11,
                    fontFamily: "'JetBrains Mono', monospace",
                    letterSpacing: "0.06em",
                  }}
                >
                  CLOSE
                </motion.button>
              </div>
            </div>

            {/* Stats Bar */}
            <AnimatePresence>
              {stats && (
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  style={{
                    display: "flex",
                    gap: 10,
                    padding: "10px 20px",
                    borderBottom: "1px solid rgba(255,255,255,0.05)",
                    flexShrink: 0,
                    overflowX: "auto",
                    alignItems: "center",
                  }}
                >
                  <StatChip label="Nodes" value={stats.totalNodes} color="#00D4FF" />
                  <StatChip label="Edges" value={stats.totalEdges} color="#00D4FF" />
                  <StatChip label="Direct" value={stats.directNeighbors} color="#4ADE80" />
                  <StatChip label="Volume ETH" value={stats.totalVolumeEth.toFixed(2)} color={stats.totalVolumeEth > 50 ? "#FF3B3B" : "#FFD700"} />
                  {stats.flaggedNeighbors > 0 && (
                    <StatChip label="Flagged" value={stats.flaggedNeighbors} color="#FF3B3B" />
                  )}
                  {error && (
                    <div style={{
                      display: "flex",
                      alignItems: "center",
                      marginLeft: "auto",
                      gap: 6,
                      fontSize: 10,
                      color: "#FFD700",
                      fontFamily: "'JetBrains Mono', monospace",
                      background: "rgba(255,215,0,0.08)",
                      border: "1px solid rgba(255,215,0,0.2)",
                      borderRadius: 6,
                      padding: "4px 10px",
                      whiteSpace: "nowrap",
                    }}>
                      {error}
                    </div>
                  )}
                </motion.div>
              )}
            </AnimatePresence>

            {/* Legend */}
            <div style={{
              display: "flex",
              gap: 16,
              padding: "6px 20px",
              borderBottom: "1px solid rgba(255,255,255,0.04)",
              flexShrink: 0,
              flexWrap: "wrap",
            }}>
              {[
                { color: "#FFFFFF", label: "Origin" },
                { color: "#4ADE80", label: "Safe" },
                { color: "#00D4FF", label: "Low" },
                { color: "#FFD700", label: "Medium" },
                { color: "#FF8C00", label: "High" },
                { color: "#FF3B3B", label: "Critical" },
              ].map(({ color, label }) => (
                <div key={label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <div style={{ width: 8, height: 8, borderRadius: "50%", background: color, boxShadow: `0 0 4px ${color}` }} />
                  <span style={{ fontSize: 10, color: "#475569", letterSpacing: "0.05em" }}>{label}</span>
                </div>
              ))}
              <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <div style={{ width: 8, height: 8, borderRadius: "50%", border: "1px dashed rgba(100,180,255,0.5)", background: "transparent" }} />
                <span style={{ fontSize: 10, color: "#475569", letterSpacing: "0.05em" }}>2-hop</span>
              </div>
            </div>

            {/* Graph Canvas */}
            <div ref={containerRef} style={{ flex: 1, position: "relative", overflow: "hidden", background: "radial-gradient(ellipse at center, #030820 0%, #000008 100%)" }}>
              {loading ? (
                <LoadingSkeleton />
              ) : data && data.nodes.length > 0 ? (
                <>
                  <ForceGraph2D
                    ref={graphRef}
                    graphData={graphData}
                    width={dimensions.width}
                    height={dimensions.height}
                    backgroundColor="rgba(0,0,0,0)"
                    nodeCanvasObject={(node, ctx, globalScale) => paintNode(node as ExplorerNode, ctx, globalScale)}
                    nodeCanvasObjectMode={() => "replace"}
                    linkCanvasObject={(link, ctx) => paintLink(link as unknown as ExplorerLink, ctx)}
                    linkCanvasObjectMode={() => "replace"}
                    onNodeClick={(node) => handleNodeClick(node as ExplorerNode)}
                    onNodeHover={(node) => setHoveredNode((node as ExplorerNode) ?? null)}
                    nodePointerAreaPaint={(node: any, color, ctx) => {
                      ctx.fillStyle = color;
                      ctx.beginPath();
                      ctx.arc(node.x, node.y, nodeSize(node as ExplorerNode) + 2, 0, Math.PI * 2);
                      ctx.fill();
                    }}
                    d3AlphaDecay={0.03}
                    d3VelocityDecay={0.3}
                    warmupTicks={80}
                    cooldownTicks={150}
                    enableZoomInteraction={true}
                    enablePanInteraction={true}
                    enableNodeDrag={true}
                  />

                  {/* Hover tooltip */}
                  <AnimatePresence>
                    {hoveredNode && (
                      <motion.div
                        key="tooltip"
                        initial={{ opacity: 0, scale: 0.92 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.92 }}
                        style={{
                          position: "absolute",
                          bottom: 16,
                          left: 16,
                          background: "rgba(2,6,23,0.95)",
                          border: `1px solid ${riskColor(hoveredNode.riskScore, hoveredNode.flagged)}55`,
                          borderRadius: 10,
                          padding: "10px 14px",
                          pointerEvents: "none",
                          backdropFilter: "blur(12px)",
                          minWidth: 220,
                        }}
                      >
                        <div style={{ fontSize: 11, fontFamily: "'JetBrains Mono', monospace", color: riskColor(hoveredNode.riskScore, hoveredNode.flagged), marginBottom: 4, fontWeight: 700, letterSpacing: "0.05em" }}>
                          {hoveredNode.isOrigin ? "ORIGIN" : hoveredNode.hopDepth === 1 ? "DIRECT" : "2-HOP"}
                          {hoveredNode.flagged && " | FLAGGED"}
                        </div>
                        <div style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: "#CBD5E1", marginBottom: 6 }}>
                          {hoveredNode.address.slice(0, 12)}...{hoveredNode.address.slice(-8)}
                        </div>
                        <div style={{ display: "flex", gap: 12 }}>
                          <div style={{ fontSize: 11, color: "#64748B" }}>
                            Risk: <span style={{ color: riskColor(hoveredNode.riskScore, hoveredNode.flagged), fontWeight: 700 }}>{(hoveredNode.riskScore * 100).toFixed(0)}%</span>
                          </div>
                          <div style={{ fontSize: 11, color: "#64748B" }}>
                            Txns: <span style={{ color: "#94A3B8" }}>{hoveredNode.txCount.toLocaleString()}</span>
                          </div>
                          <div style={{ fontSize: 11, color: "#64748B" }}>
                            ETH: <span style={{ color: "#94A3B8" }}>{hoveredNode.balanceEth.toFixed(2)}</span>
                          </div>
                        </div>
                        <div style={{ marginTop: 8, fontSize: 10, color: "#475569" }}>
                          {pathMode ? "Click to select for path trace" : "Click to inspect in sidebar"}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 12, color: "#475569", fontFamily: "'JetBrains Mono', monospace", fontSize: 13 }}>
                  <span style={{ fontSize: 28 }}>No connections found within 2 hops</span>
                </div>
              )}
            </div>

            {/* Footer */}
            <div style={{
              padding: "8px 20px",
              borderTop: "1px solid rgba(255,255,255,0.05)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexShrink: 0,
            }}>
              <span style={{ fontSize: 10, color: "#334155", fontFamily: "'JetBrains Mono', monospace", letterSpacing: "0.06em" }}>
                SCROLL to zoom  DRAG nodes  CLICK to inspect  ESC to close
              </span>
              {pathMode && selectedPath.size > 1 && (
                <motion.span
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  style={{ fontSize: 10, color: "#A78BFA", fontFamily: "'JetBrains Mono', monospace", letterSpacing: "0.06em" }}
                >
                  PATH: {selectedPath.size} hops
                </motion.span>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
