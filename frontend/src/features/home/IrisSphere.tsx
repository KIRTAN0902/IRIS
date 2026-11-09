import { useEffect, useRef } from "react";
import type { VoicePhase } from "@/features/home/voice";

/**
 * IRIS Signature Sphere: Intricate Geometric Intelligence Core (Matte Black Edition)
 *
 * Inspired by sacred geometry and multi-layered polyhedral mandalas.
 * Features:
 * - Layer 1: Outer 16-faceted geodesic boundary with polygonal cross-ties
 * - Layer 2: Intermediate sacred 8-fold double-chevron arrow crowns with diamond facets
 * - Layer 3: Inner 16-point multi-star sacred rosette with harmonic counter-rotation
 * - Layer 4: Central geometric focal nucleus with concentric regular hexagons and focal core
 *
 * Matte Black & Deep Graphite Palette:
 * - High-contrast charcoal and deep slate against daylight interface
 * - Depth-sorted line weights and atmospheric opacity gradients
 * - Precision obsidian vertex nodes with subtle slate edge micro-sheens
 *
 * Reactive Kinetics:
 * - Idle: Serene celestial precessional drift
 * - Listening: Mic-reactive acoustic iris expansion
 * - Thinking: Harmonic multi-layer counter-acceleration
 * - Speaking: Syllabic cadence pulse of the inner rosette and focal core
 * - Paused: Resting low-frequency state
 */

interface Props {
  phase: VoicePhase;
  /** Live input level, 0..1 (mic loudness while listening). */
  level: () => number;
  size: number;
}

// 3D Matrix Math Helpers
function rotY(v: [number, number, number], a: number): [number, number, number] {
  const c = Math.cos(a), s = Math.sin(a);
  return [v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c];
}
function rotX(v: [number, number, number], a: number): [number, number, number] {
  const c = Math.cos(a), s = Math.sin(a);
  return [v[0], v[1] * c - v[2] * s, v[1] * s + v[2] * c];
}
function rotZ(v: [number, number, number], a: number): [number, number, number] {
  const c = Math.cos(a), s = Math.sin(a);
  return [v[0] * c - v[1] * s, v[0] * s + v[1] * c, v[2]];
}

interface NodeDef {
  pos: [number, number, number];
  layer: number;
  type: string;
}

interface EdgeDef {
  a: number;
  b: number;
  layer: number;
  weight: number;
}

/** Pre-compute the sacred geometry topology once */
function buildSignatureSacredGeometry() {
  const nodes: NodeDef[] = [];
  const edges: EdgeDef[] = [];
  const edgeSet = new Set<string>();

  function addNode(x: number, y: number, z: number, layer: number, type: string): number {
    const idx = nodes.length;
    nodes.push({ pos: [x, y, z], layer, type });
    return idx;
  }

  function addEdge(a: number, b: number, layer: number, weight = 1) {
    if (a === b) return;
    const k = a < b ? `${a}-${b}` : `${b}-${a}`;
    if (!edgeSet.has(k)) {
      edgeSet.add(k);
      edges.push({ a, b, layer, weight });
    }
  }

  function spherePt(rNorm: number, theta: number, zOffset = 0, rShell = 1.0): [number, number, number] {
    const clampedR = Math.min(0.999, rNorm);
    const x = clampedR * Math.cos(theta);
    const y = clampedR * Math.sin(theta);
    const z = (Math.sqrt(Math.max(0, 1 - clampedR * clampedR)) * 0.48) + zOffset;
    return [x * rShell, y * rShell, z * rShell];
  }

  // --- 1. OUTER GEODESIC LATTICE (16 Outer Nodes + Collar Webbing) ---
  const outerNodes: number[] = [];
  const SECTORS = 16;
  for (let i = 0; i < SECTORS; i++) {
    const th = (i * 2 * Math.PI) / SECTORS;
    const pt = spherePt(0.96, th, 0, 1.0);
    outerNodes.push(addNode(pt[0], pt[1], pt[2], 1, "outer-rim"));
  }

  for (let i = 0; i < SECTORS; i++) {
    addEdge(outerNodes[i], outerNodes[(i + 1) % SECTORS], 1, 1.35);
    addEdge(outerNodes[i], outerNodes[(i + 2) % SECTORS], 1, 0.7);  // outer faceted chord
    addEdge(outerNodes[i], outerNodes[(i + 3) % SECTORS], 1, 0.6);  // star stellation {16/3}
  }

  // Intermediate Geodesic Collar (16 nodes staggered)
  const subRimNodes: number[] = [];
  for (let i = 0; i < SECTORS; i++) {
    const th = (i * 2 * Math.PI) / SECTORS + (Math.PI / SECTORS);
    const pt = spherePt(0.87, th, 0.06, 1.0);
    subRimNodes.push(addNode(pt[0], pt[1], pt[2], 1, "sub-rim"));
  }
  for (let i = 0; i < SECTORS; i++) {
    const nxt = (i + 1) % SECTORS;
    addEdge(subRimNodes[i], subRimNodes[nxt], 1, 0.95);
    addEdge(outerNodes[i], subRimNodes[i], 1, 0.85);
    addEdge(outerNodes[nxt], subRimNodes[i], 1, 0.85);
  }

  // --- 2. SACRED CHEVRON CROWNS (Layered 8-Fold Architecture) ---
  const chevCount = 8;
  const chevrons: Array<{
    peak: number; subPeak: number;
    wingL: number; wingR: number;
    subWingL: number; subWingR: number;
    valley: number;
  }> = [];

  for (let i = 0; i < chevCount; i++) {
    const thCenter = (i * 2 * Math.PI) / chevCount;
    const thL = thCenter - (Math.PI / 15);
    const thR = thCenter + (Math.PI / 15);
    const thInnerL = thCenter - (Math.PI / 28);
    const thInnerR = thCenter + (Math.PI / 28);

    // Peak 1: Sharp outer arrow tip
    const ptPeak = spherePt(0.85, thCenter, 0.09, 1.0);
    // Peak 2: Nested double-chevron peak
    const ptSubPeak = spherePt(0.70, thCenter, 0.13, 1.0);
    // Wings
    const ptWingL = spherePt(0.67, thL, 0.07, 1.0);
    const ptWingR = spherePt(0.67, thR, 0.07, 1.0);
    const ptSubWingL = spherePt(0.56, thInnerL, 0.11, 1.0);
    const ptSubWingR = spherePt(0.56, thInnerR, 0.11, 1.0);
    // Valley base
    const ptValley = spherePt(0.44, thCenter, 0.15, 1.0);

    const idxPeak = addNode(ptPeak[0], ptPeak[1], ptPeak[2], 2, "chev-peak");
    const idxSubPeak = addNode(ptSubPeak[0], ptSubPeak[1], ptSubPeak[2], 2, "chev-subpeak");
    const idxWingL = addNode(ptWingL[0], ptWingL[1], ptWingL[2], 2, "chev-wing");
    const idxWingR = addNode(ptWingR[0], ptWingR[1], ptWingR[2], 2, "chev-wing");
    const idxSubWingL = addNode(ptSubWingL[0], ptSubWingL[1], ptSubWingL[2], 2, "chev-subwing");
    const idxSubWingR = addNode(ptSubWingR[0], ptSubWingR[1], ptSubWingR[2], 2, "chev-subwing");
    const idxValley = addNode(ptValley[0], ptValley[1], ptValley[2], 2, "chev-valley");

    chevrons.push({
      peak: idxPeak, subPeak: idxSubPeak,
      wingL: idxWingL, wingR: idxWingR,
      subWingL: idxSubWingL, subWingR: idxSubWingR,
      valley: idxValley
    });

    // Outer chevron diamond facet lines
    addEdge(idxWingL, idxPeak, 2, 1.4);
    addEdge(idxWingR, idxPeak, 2, 1.4);
    addEdge(idxWingL, idxValley, 2, 0.95);
    addEdge(idxWingR, idxValley, 2, 0.95);

    // Nested inner chevron lines
    addEdge(idxSubWingL, idxSubPeak, 2, 1.15);
    addEdge(idxSubWingR, idxSubPeak, 2, 1.15);
    addEdge(idxSubWingL, idxValley, 2, 0.85);
    addEdge(idxSubWingR, idxValley, 2, 0.85);

    // Internal cross-bracing triangular struts
    addEdge(idxWingL, idxSubWingL, 2, 0.85);
    addEdge(idxWingR, idxSubWingR, 2, 0.85);
    addEdge(idxSubPeak, idxPeak, 2, 0.9); // spine rib

    // Radial anchor struts to outer collar
    addEdge(idxPeak, outerNodes[i * 2], 1.5, 0.85);
    addEdge(idxWingL, subRimNodes[i * 2], 1.5, 0.7);
    addEdge(idxWingR, subRimNodes[(i * 2 + 1) % SECTORS], 1.5, 0.7);
  }

  // Connecting adjacent chevron wings to form continuous crown ring
  for (let i = 0; i < chevCount; i++) {
    const next = (i + 1) % chevCount;
    addEdge(chevrons[i].wingR, chevrons[next].wingL, 2, 1.1);
    addEdge(chevrons[i].valley, chevrons[next].valley, 2, 0.85);

    // Sacred star chords {8/3} connecting alternate chevron peaks
    addEdge(chevrons[i].peak, chevrons[(i + 3) % chevCount].peak, 2, 0.7);
    // Inter-valley diamond webbing
    addEdge(chevrons[i].subPeak, chevrons[next].valley, 2, 0.65);
    addEdge(chevrons[next].subPeak, chevrons[i].valley, 2, 0.65);
  }

  // --- 3. INNER SACRED ROSETTE & WEBBING (16-Point Multi-Star Mandala) ---
  const rosette16: number[] = [];
  for (let i = 0; i < 16; i++) {
    const th = (i * 2 * Math.PI) / 16;
    const rNorm = (i % 2 === 0) ? 0.38 : 0.25;
    const pt = spherePt(rNorm, th, 0.17, 1.0);
    rosette16.push(addNode(pt[0], pt[1], pt[2], 3, "rosette-node"));
  }

  for (let i = 0; i < 16; i++) {
    addEdge(rosette16[i], rosette16[(i + 1) % 16], 3, 1.25);
    addEdge(rosette16[i], rosette16[(i + 4) % 16], 3, 0.65); // square star stellation
    addEdge(rosette16[i], rosette16[(i + 5) % 16], 3, 0.7);  // multi-star stellation
  }

  // Radial chords from chevron valleys to rosette nodes
  for (let i = 0; i < chevCount; i++) {
    addEdge(chevrons[i].valley, rosette16[i * 2], 2.5, 0.95);
    addEdge(chevrons[i].subPeak, rosette16[(i * 2 + 1) % 16], 2.5, 0.8);
  }

  // --- 4. CENTRAL GEOMETRIC FOCAL NUCLEUS (Hexagon & Concentric Micro-Core) ---
  const hexOuter: number[] = [];
  for (let i = 0; i < 6; i++) {
    const th = (i * 2 * Math.PI) / 6;
    const pt = spherePt(0.16, th, 0.22, 1.0);
    hexOuter.push(addNode(pt[0], pt[1], pt[2], 4, "hex-outer"));
  }
  for (let i = 0; i < 6; i++) {
    addEdge(hexOuter[i], hexOuter[(i + 1) % 6], 4, 1.5);
  }

  // Concentric Micro-Hexagon (rotated 30 deg)
  const hexInner: number[] = [];
  for (let i = 0; i < 6; i++) {
    const th = (i * 2 * Math.PI) / 6 + (Math.PI / 6);
    const pt = spherePt(0.07, th, 0.24, 1.0);
    hexInner.push(addNode(pt[0], pt[1], pt[2], 4, "hex-inner"));
  }
  for (let i = 0; i < 6; i++) {
    addEdge(hexInner[i], hexInner[(i + 1) % 6], 4, 1.2);
    addEdge(hexOuter[i], hexInner[i], 4, 1.05); // radial spoke
  }

  // Central Nucleus Dot
  const nucleus = addNode(0, 0, 0.26, 4, "nucleus");
  for (let i = 0; i < 6; i++) {
    addEdge(nucleus, hexInner[i], 4, 1.35);
  }

  // Connect Hexagon to Rosette
  for (let i = 0; i < 6; i++) {
    addEdge(hexOuter[i], rosette16[Math.floor((i * 16) / 6)], 3.5, 0.9);
  }

  return { nodes, edges };
}

// Global cached geometry model for high-efficiency rendering
const MODEL = buildSignatureSacredGeometry();

export function IrisSphere({ phase, level, size }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const phaseRef = useRef(phase);
  phaseRef.current = phase;
  const levelRef = useRef(level);
  levelRef.current = level;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

    const c = size / 2;
    let spinZ = 0;
    let shown = 0; // smoothed audio reactivity
    let lastTime = performance.now();
    let frame = 0;

    function project(
      node: NodeDef,
      r: number,
      rZ: number,
      pitchX: number,
      yawY: number,
      scaleBoost = 1.0,
    ) {
      let v: [number, number, number] = [
        node.pos[0] * scaleBoost,
        node.pos[1] * scaleBoost,
        node.pos[2] * scaleBoost,
      ];

      // 1. In-plane celestial geometric rotation around Z
      v = rotZ(v, rZ);

      // 2. Subtle 3D precessional pitch and yaw (creates gentle spherical parallax)
      v = rotX(v, pitchX);
      v = rotY(v, yawY);

      const dist = 3.4;
      const px = v[0] * r;
      const py = v[1] * r;
      const pz = v[2] * r;

      const persp = dist / (dist - pz / r);
      return {
        x: c + px * persp,
        y: c + py * persp,
        z: pz / r,
        persp,
        layer: node.layer,
        type: node.type,
      };
    }

    const draw = (now: number) => {
      const dt = Math.min((now - lastTime) / 1000, 0.05);
      lastTime = now;
      const p = phaseRef.current;
      const t = now / 1000;

      // Real-time assistant state reactivity
      let target = 0.05;
      if (p === "listening") {
        target = Math.min(1, levelRef.current());
      } else if (p === "paused") {
        target = 0.02;
      } else if (p === "speaking") {
        target = 0.35 + 0.28 * Math.abs(Math.sin(t * 7.2)) * (0.6 + 0.4 * Math.sin(t * 2.1 + 1.2));
      } else if (p === "thinking" || p === "transcribing") {
        target = 0.2 + 0.1 * Math.sin(t * 5.5);
      }
      shown += (target - shown) * Math.min(1, dt * 10);

      // Animation speed modulated by state
      const baseSpeed = reduceMotion
        ? 0
        : p === "thinking" || p === "transcribing"
        ? 0.55
        : p === "speaking"
        ? 0.22
        : p === "paused"
        ? 0.04
        : 0.12 + shown * 0.18;

      spinZ += baseSpeed * dt;

      // Subtle 3D precessional wobble (creates living spherical depth)
      const pitchX = reduceMotion ? 0.08 : Math.sin(now * 0.00045) * 0.12;
      const yawY = reduceMotion ? 0.08 : Math.cos(now * 0.00035) * 0.12;

      // Base radius with subtle voice expansion
      const baseR = size * 0.44 * (1 + shown * 0.06);

      ctx.clearRect(0, 0, size, size);

      // Project nodes with harmonic layer counter-rotations
      const projected = MODEL.nodes.map((n) => {
        let layerZ = spinZ;
        let scaleBoost = 1.0;

        if (n.layer === 1) {
          // Outer Geodesic Boundary: turns slowly clockwise
          layerZ = spinZ * 0.75;
        } else if (n.layer === 2) {
          // Sacred Chevron Crowns: primary baseline rotation (expands subtly when listening)
          layerZ = spinZ;
          scaleBoost = 1.0 + shown * 0.04;
        } else if (n.layer === 3) {
          // Inner Rosette: delicate counter-rotation (kaleidoscope effect)
          layerZ = -spinZ * 0.55;
          if (p === "speaking") scaleBoost = 1.0 + 0.06 * Math.sin(t * 8);
        } else if (n.layer === 4) {
          // Central Hexagonal Nucleus: clockwise harmonic with speech pulse
          layerZ = spinZ * 1.35;
          if (p === "speaking") scaleBoost = 1.0 + 0.09 * Math.sin(t * 8);
        }

        return project(n, baseR, layerZ, pitchX, yawY, scaleBoost);
      });

      // Unified 3D depth-sorting for all edges
      const sortedEdges = MODEL.edges.map((e) => {
        const pa = projected[e.a];
        const pb = projected[e.b];
        const depth = (pa.z + pb.z) / 2;
        return { pa, pb, depth, layer: e.layer, weight: e.weight };
      }).sort((a, b) => a.depth - b.depth);

      // 1. DRAW EDGES IN MATTE BLACK & DEEP GRAPHITE
      for (const { pa, pb, depth, weight } of sortedEdges) {
        ctx.beginPath();
        ctx.moveTo(pa.x, pa.y);
        ctx.lineTo(pb.x, pb.y);

        const depth01 = (depth + 1) / 2; // 0..1

        if (depth < -0.1) {
          // Receding back edges: muted slate-grey
          ctx.lineWidth = (size > 100 ? 0.6 : 0.48) * weight;
          const a = 0.18 + 0.18 * (depth + 1);
          ctx.strokeStyle = `rgba(71, 85, 105, ${a.toFixed(3)})`;
        } else if (depth < 0.2) {
          // Mid-depth geometry: deep graphite
          ctx.lineWidth = (size > 100 ? 0.8 : 0.62) * weight;
          const a = 0.45 + 0.35 * depth01;
          ctx.strokeStyle = `rgba(30, 41, 59, ${a.toFixed(3)})`;
        } else {
          // Foreground geometry: crisp matte black & charcoal
          ctx.lineWidth = (size > 100 ? 1.05 : 0.75) * weight;
          const a = 0.75 + 0.25 * depth01;
          ctx.strokeStyle = `rgba(15, 23, 42, ${a.toFixed(3)})`;
        }

        ctx.stroke();
      }

      // 2. DRAW PRECISION VERTEX NODES
      projected.forEach((node) => {
        const d = (node.z + 1) / 2;

        if (node.type === "chev-peak") {
          const rad = size > 100 ? 2.0 + 1.2 * d : 1.4;
          ctx.beginPath();
          ctx.arc(node.x, node.y, rad, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(2, 6, 23, ${(0.6 + 0.4 * d).toFixed(3)})`;
          ctx.fill();
          if (size > 100) {
            ctx.lineWidth = 0.6;
            ctx.strokeStyle = "rgba(100, 116, 139, 0.45)";
            ctx.stroke();
          }
        } else if (node.type === "outer-rim") {
          const rad = size > 100 ? 1.5 + 0.9 * d : 1.1;
          ctx.beginPath();
          ctx.arc(node.x, node.y, rad, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(15, 23, 42, ${(0.4 + 0.6 * d).toFixed(3)})`;
          ctx.fill();
        } else if (node.type === "nucleus") {
          // Central core focal nucleus
          const rNuc = (size > 100 ? 2.8 : 1.6) * (1 + shown * 0.15);
          ctx.beginPath();
          ctx.arc(node.x, node.y, rNuc, 0, Math.PI * 2);
          ctx.fillStyle = "#020617";
          ctx.fill();
          ctx.lineWidth = 0.8;
          ctx.strokeStyle = "rgba(71, 85, 105, 0.8)";
          ctx.stroke();
        }
      });

      frame = requestAnimationFrame(draw);
    };

    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [size]);

  return <canvas ref={canvasRef} style={{ width: size, height: size }} aria-hidden className="block" />;
}
