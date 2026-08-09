/**
 * Galaxy3D.tsx — 3D Force Graph Visualization
 */

import { useCallback, useEffect, useRef, useState } from "react";
import ForceGraph3D from "react-force-graph-3d";
import * as THREE from "three";

// Store references to attacker meshes for 60fps pulsing animation
const _attackerMeshes = new Set<{ core: THREE.Mesh; halo: THREE.Mesh }>();

let animationFrameId: number;
const startPulsing = () => {
  let t = 0;
  const animate = () => {
    t += 0.05;
    const scale = 0.8 + 0.5 * Math.abs(Math.sin(t));
    const haloOpacity = 0.15 + 0.2 * Math.abs(Math.sin(t));

    _attackerMeshes.forEach(({ core, halo }) => {
      core.scale.set(scale, scale, scale);
      halo.scale.set(scale, scale, scale);
      if (halo.material instanceof THREE.MeshBasicMaterial) {
        halo.material.opacity = haloOpacity;
      }
    });
    animationFrameId = requestAnimationFrame(animate);
  };
  animate();
};



// ── Types ──────────────────────────────────────────────────────
export interface GalaxyNode {
  id: string;             // wallet address (0x...)
  address: string;
  label: "defi_user" | "bot" | "exchange" | "whale" | "attacker" | "unknown";
  riskScore: number;      // 0.0 → 1.0
  flagged: boolean;
  txCount: number;
  balanceEth: number;
  x?: number;
  y?: number;
  z?: number;
  __threeObj?: THREE.Object3D;
}

export interface GalaxyLink {
  source: string;         // from wallet address
  target: string;         // to wallet address
  txHash: string;
  valueEth: number;
}

export interface GraphData {
  nodes: GalaxyNode[];
  links: GalaxyLink[];
}

interface Galaxy3DProps {
  /** Data fetched from /api/graph/nodes */
  graphData: GraphData;
  /** Callback when a node is clicked — triggers Sidebar update */
  onNodeSelect: (node: GalaxyNode) => void;
  /** Currently selected node (highlighted in galaxy) */
  selectedNode: GalaxyNode | null;
  /** Whether the galaxy is in "alert mode" (flashing red) */
  alertMode?: boolean;
}

// ── Risk Color Mapping ─────────────────────────────────────────
function riskToColor(riskScore: number, flagged: boolean): string {
  if (flagged || riskScore > 0.85) return "#FF3B3B";   // Critical — deep red
  if (riskScore > 0.65) return "#FF8C00";              // High — amber
  if (riskScore > 0.40) return "#FFD700";              // Medium — gold
  if (riskScore > 0.20) return "#00D4FF";              // Low — cyan
  return "#4ADE80";                                    // Safe — green
}

function labelToSize(label: GalaxyNode["label"], riskScore: number): number {
  const base = label === "whale" ? 6 : label === "exchange" ? 5 : 3;
  return base + riskScore * 4; // Higher risk = larger node
}

// ── Component ──────────────────────────────────────────────────
export default function Galaxy3D({
  graphData,
  onNodeSelect,
  selectedNode,
  alertMode = false,
}: Galaxy3DProps) {
  const graphRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  // Responsive resize
  useEffect(() => {
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        });
      }
    });
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  // Clear stale attacker meshes
  useEffect(() => {
    _attackerMeshes.clear();
  }, [graphData]);

  // Animation loop
  useEffect(() => {
    startPulsing();
    return () => cancelAnimationFrame(animationFrameId);
  }, []);

  // Auto-zoom to selected node
  useEffect(() => {
    if (selectedNode && graphRef.current) {
      graphRef.current.cameraPosition(
        { x: (selectedNode.x ?? 0) + 80, y: selectedNode.y ?? 0, z: selectedNode.z ?? 0 },
        { x: selectedNode.x ?? 0, y: selectedNode.y ?? 0, z: selectedNode.z ?? 0 },
        1200,
      );
    }
  }, [selectedNode]);




  const nodeThreeObject = useCallback(
    (node: GalaxyNode) => {
      const isAttacker = node.label === "attacker";
      const isSelected = selectedNode?.id === node.id;
      const color = isAttacker ? "#FF1111" : riskToColor(node.riskScore, node.flagged);
      const baseSize = labelToSize(node.label, node.riskScore);
      const size = isSelected ? baseSize * 1.5 : baseSize;

      const geometry = new THREE.SphereGeometry(size, isAttacker ? 16 : 8, isAttacker ? 16 : 8);
      const material = new THREE.MeshBasicMaterial({ color: new THREE.Color(color) });
      const mesh = new THREE.Mesh(geometry, material);

      // Glow halo
      if (isAttacker || isSelected || node.flagged) {
        const haloSize = isAttacker ? size * 3.5 : size * 2.5;
        const haloGeo = new THREE.SphereGeometry(haloSize, 16, 16);
        const haloMat = new THREE.MeshBasicMaterial({
          color: new THREE.Color(color),
          transparent: true,
          opacity: 0.12,
          side: THREE.BackSide,
        });
        const haloMesh = new THREE.Mesh(haloGeo, haloMat);
        
        const group = new THREE.Group();
        group.add(mesh);
        group.add(haloMesh);

        if (isAttacker) {
          // Register for animation loop
          _attackerMeshes.add({ core: mesh, halo: haloMesh });
        }

        return group;
      }

      return mesh;
    },
    [selectedNode]
  );


  // Link color based on transaction value
  const linkColor = useCallback((link: GalaxyLink) => {
    if (link.valueEth > 10) return "#FF3B3B";
    if (link.valueEth > 1) return "#FF8C00";
    return "rgba(100, 200, 255, 0.3)";
  }, []);

  const linkWidth = useCallback((link: GalaxyLink) => {
    return Math.min(0.5 + link.valueEth * 0.1, 3);
  }, []);

  return (
    <div
      ref={containerRef}
      className="galaxy-container"
      style={{
        width: "100%",
        height: "100%",
        position: "relative",
        background: alertMode
          ? "radial-gradient(ellipse at center, #1a0000 0%, #0a0010 100%)"
          : "radial-gradient(ellipse at center, #0a0020 0%, #000008 100%)",
        transition: "background 0.5s ease",
      }}
    >
      {/* Ambient overlay — star field effect */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage:
            "radial-gradient(1px 1px at 20px 30px, rgba(255,255,255,0.15), transparent), " +
            "radial-gradient(1px 1px at 80px 60px, rgba(255,255,255,0.1), transparent), " +
            "radial-gradient(1px 1px at 140px 100px, rgba(255,255,255,0.12), transparent)",
          backgroundSize: "200px 200px",
          pointerEvents: "none",
          zIndex: 1,
        }}
      />

      {/* Node count badge */}
      <div
        style={{
          position: "absolute",
          top: 16,
          left: 16,
          zIndex: 10,
          background: "rgba(0,0,0,0.6)",
          border: "1px solid rgba(0, 212, 255, 0.3)",
          borderRadius: 8,
          padding: "6px 12px",
          color: "#00D4FF",
          fontSize: 12,
          fontFamily: "'JetBrains Mono', monospace",
          backdropFilter: "blur(8px)",
        }}
      >
        ⬡ {graphData.nodes.length.toLocaleString()} nodes · {graphData.links.length.toLocaleString()} edges
      </div>

      {/* Alert mode banner */}
      {alertMode && (
        <div
          style={{
            position: "absolute",
            top: 16,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 10,
            background: "rgba(255,59,59,0.15)",
            border: "1px solid #FF3B3B",
            borderRadius: 8,
            padding: "6px 20px",
            color: "#FF3B3B",
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: "0.1em",
            animation: "pulse 1.5s ease-in-out infinite",
          }}
        >
          🚨 THREAT DETECTED — Third Eye ACTIVE
        </div>
      )}

      <ForceGraph3D
        ref={graphRef}
        graphData={graphData}
        width={dimensions.width}
        height={dimensions.height}
        backgroundColor="rgba(0,0,0,0)"
        nodeThreeObject={nodeThreeObject}
        nodeThreeObjectExtend={false}
        nodeLabel={(node: GalaxyNode) =>
          `${node.address.slice(0, 8)}…${node.address.slice(-4)} | Risk: ${(node.riskScore * 100).toFixed(1)}%`
        }
        onNodeClick={(node: GalaxyNode) => onNodeSelect(node)}
        linkColor={linkColor}
        linkWidth={linkWidth}
        linkOpacity={0.3}
        linkDirectionalParticles={0}
        enableNodeDrag={true}
        enableNavigationControls={true}
        showNavInfo={false}
        d3AlphaDecay={0.04}
        d3VelocityDecay={0.4}
        warmupTicks={100}
        cooldownTicks={200}
      />
    </div>
  );
}
