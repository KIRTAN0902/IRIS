import { useEffect, useRef } from "react";
import type { VoicePhase } from "@/features/home/voice";

/**
 * The IRIS Sphere: Exact Signature Geometric Intelligence Core in 3D Matte Black / Obsidian.
 *
 * Preserves 100% of the exact geometric structure from the reference model:
 * - 96-node Fibonacci lattice on a unit sphere
 * - Deduplicated nearest-neighbor links (3 links per node)
 * - Concentric turning 12-point star
 * - Central turning regular hexagon with vertex nodes
 * - Central 3D obsidian focal core
 *
 * True 3D Volumetric Depth:
 * - True painter's algorithm depth sorting (back wireframe -> back nodes -> internal star/hex -> front wireframe -> front nodes)
 * - Front vertices are volumetric obsidian beads with directional top-left specular highlights
 * - Front edges are crisp, bold dark obsidian; back edges softly recede in slate-grey
 * - 100% transparent canvas background (no white container, no fuzzy glow smudge)
 */

const NODES = 96;
const LINKS_PER_NODE = 3;

interface Props {
  phase: VoicePhase;
  /** Live input level, 0..1 (mic loudness while listening). */
  level: () => number;
  size: number;
}

type Vec = [number, number, number];

/** Evenly spread points on a unit sphere (Fibonacci lattice). */
function fibonacciSphere(n: number): Vec[] {
  const pts: Vec[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const t = golden * i;
    pts.push([Math.cos(t) * r, y, Math.sin(t) * r]);
  }
  return pts;
}

/** Each node joined to its nearest neighbours (deduplicated). */
function nearestLinks(pts: Vec[], k: number): [number, number][] {
  const seen = new Set<string>();
  const links: [number, number][] = [];
  pts.forEach((p, i) => {
    pts
      .map((q, j) => ({ j, d: (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2 }))
      .filter((x) => x.j !== i)
      .sort((a, b) => a.d - b.d)
      .slice(0, k)
      .forEach(({ j }) => {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`;
        if (!seen.has(key)) {
          seen.add(key);
          links.push([i, j]);
        }
      });
  });
  return links;
}

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
    const pts = fibonacciSphere(NODES);
    const links = nearestLinks(pts, LINKS_PER_NODE);
    const projected = pts.map(() => ({ x: 0, y: 0, z: 0, s: 1 }));

    const c = size / 2;
    let rotY = 0.5;
    let rotX = 0.34;
    let spin = 0;
    let shown = 0; // smoothed level actually drawn
    let last = performance.now();
    let frame = 0;

    const draw = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      const p = phaseRef.current;
      const t = now / 1000;

      // Real mic level while listening, speech pulse while speaking, shimmer while thinking
      let target = 0.06;
      if (p === "listening") target = Math.min(1, levelRef.current());
      else if (p === "paused") target = 0.04;
      else if (p === "speaking")
        target = 0.35 + 0.3 * Math.abs(Math.sin(t * 7.3)) * (0.6 + 0.4 * Math.sin(t * 2.1 + 1.3));
      else if (p === "thinking" || p === "transcribing") target = 0.22 + 0.1 * Math.sin(t * 5);
      shown += (target - shown) * Math.min(1, dt * 10);

      const speed = reduceMotion ? 0 : p === "thinking" || p === "transcribing" ? 1.4 : 0.4 + shown * 0.6;
      rotY += speed * dt;
      rotX = 0.34 + Math.sin(t * 0.4) * 0.12;
      spin += (reduceMotion ? 0 : speed * 0.65) * dt;

      const R = size * 0.38 * (1 + shown * 0.12);
      const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
      const cosX = Math.cos(rotX), sinX = Math.sin(rotX);

      pts.forEach(([x, y, z], i) => {
        const x1 = x * cosY + z * sinY;
        const z1 = -x * sinY + z * cosY;
        const y2 = y * cosX - z1 * sinX;
        const z2 = y * sinX + z1 * cosX;
        const persp = 2.6 / (2.6 - z2);
        const o = projected[i];
        o.x = c + x1 * R * persp;
        o.y = c + y2 * R * persp;
        o.z = z2;
        o.s = persp;
      });

      // 100% Transparent canvas background
      ctx.clearRect(0, 0, size, size);

      const sRatio = size / 100;

      // ========================================================
      // LAYER 1: BACK WIREFRAME (z <= 0) - Receding softly in depth
      // ========================================================
      links.forEach(([a, b]) => {
        const pa = projected[a], pb = projected[b];
        const depth = (pa.z + pb.z) / 2;
        if (depth <= 0) {
          const front = (depth + 1) / 2; // 0..0.5
          ctx.lineWidth = Math.max(0.65, (0.45 + 0.35 * front) * sRatio);
          ctx.strokeStyle = `rgba(100, 116, 139, ${(0.12 + 0.25 * front) * (1 + shown * 0.3)})`;
          ctx.beginPath();
          ctx.moveTo(pa.x, pa.y);
          ctx.lineTo(pb.x, pb.y);
          ctx.stroke();
        }
      });

      // ========================================================
      // LAYER 2: BACK NODES (z <= 0) - Subtle receding vertices
      // ========================================================
      projected.forEach((o) => {
        if (o.z <= 0) {
          const front = (o.z + 1) / 2; // 0..0.5
          const r = Math.max(0.8, (0.8 + front * 1.1) * sRatio);
          ctx.fillStyle = `rgba(71, 85, 105, ${(0.35 + 0.35 * front) * (1 + shown * 0.3)})`;
          ctx.beginPath();
          ctx.arc(o.x, o.y, r, 0, Math.PI * 2);
          ctx.fill();
        }
      });

      // ========================================================
      // LAYER 3: INTERNAL GEOMETRIC CORE (Inside the sphere)
      // ========================================================
      const star = (radius: number, inner: number, points: number, rot: number, alpha: number, w: number) => {
        ctx.lineWidth = Math.max(0.7, w * sRatio * 0.7);
        ctx.strokeStyle = `rgba(15, 23, 42, ${alpha * (1 + shown * 0.4)})`;
        ctx.beginPath();
        for (let k = 0; k <= points * 2; k++) {
          const ang = rot + (k * Math.PI) / points - Math.PI / 2;
          const rr = k % 2 === 0 ? radius : inner;
          const x = c + Math.cos(ang) * rr;
          const y = c + Math.sin(ang) * rr;
          if (k === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      };

      // Concentric turning 12-point star
      star(R * 0.65, R * 0.44, 12, -spin, 0.62, 1.35);

      // Inner regular hexagon
      star(R * 0.22, R * 0.22, 3, spin * 1.4, 0.8, 1.4);

      // Hexagon vertex nodes
      for (let k = 0; k < 6; k++) {
        const ang = spin * 1.4 + (k * Math.PI) / 3 - Math.PI / 2;
        const x = c + Math.cos(ang) * (R * 0.22);
        const y = c + Math.sin(ang) * (R * 0.22);
        ctx.fillStyle = "rgba(15, 23, 42, 0.85)";
        ctx.beginPath();
        ctx.arc(x, y, Math.max(1, 1.2 * sRatio), 0, Math.PI * 2);
        ctx.fill();
      }

      // Central focal core: 3D obsidian bead with specular gleam
      const coreR = Math.max(2.5, R * (0.11 + shown * 0.05));
      const coreGrad = ctx.createRadialGradient(
        c - coreR * 0.32, c - coreR * 0.32, coreR * 0.05,
        c, c, coreR
      );
      coreGrad.addColorStop(0, "rgba(255, 255, 255, 0.95)"); // specular highlight
      coreGrad.addColorStop(0.2, "rgba(160, 175, 195, 0.9)");
      coreGrad.addColorStop(0.65, "rgba(24, 32, 47, 0.98)");
      coreGrad.addColorStop(1, "rgba(10, 15, 26, 1)");
      ctx.fillStyle = coreGrad;
      ctx.beginPath();
      ctx.arc(c, c, coreR, 0, Math.PI * 2);
      ctx.fill();

      // ========================================================
      // LAYER 4: FRONT WIREFRAME (z > 0) - Crisp obsidian in foreground
      // ========================================================
      links.forEach(([a, b]) => {
        const pa = projected[a], pb = projected[b];
        const depth = (pa.z + pb.z) / 2;
        if (depth > 0) {
          const front = (depth + 1) / 2; // 0.5..1.0
          ctx.lineWidth = Math.max(0.85, (0.55 + 0.65 * front) * sRatio);
          ctx.strokeStyle = `rgba(15, 23, 42, ${(0.45 + 0.5 * front) * (1 + shown * 0.2)})`;
          ctx.beginPath();
          ctx.moveTo(pa.x, pa.y);
          ctx.lineTo(pb.x, pb.y);
          ctx.stroke();
        }
      });

      // ========================================================
      // LAYER 5: FRONT NODES (z > 0) - Volumetric obsidian beads with specular reflection
      // ========================================================
      projected.forEach((o) => {
        if (o.z > 0) {
          const front = (o.z + 1) / 2; // 0.5..1.0
          const r = Math.max(1.4, (1.1 + front * 1.5) * sRatio);

          // Shading with directional light from top-left (-0.32 * r)
          const beadGrad = ctx.createRadialGradient(
            o.x - r * 0.32, o.y - r * 0.32, r * 0.04,
            o.x, o.y, r
          );
          beadGrad.addColorStop(0, "rgba(255, 255, 255, 0.95)"); // crisp specular gleam
          beadGrad.addColorStop(0.22, "rgba(160, 175, 195, 0.85)"); // silvery graphite reflection
          beadGrad.addColorStop(0.65, "rgba(30, 41, 59, 0.96)");   // deep obsidian body
          beadGrad.addColorStop(1, "rgba(10, 15, 26, 1)");       // dark rim

          ctx.fillStyle = beadGrad;
          ctx.beginPath();
          ctx.arc(o.x, o.y, r, 0, Math.PI * 2);
          ctx.fill();

          // Specular pinprick on front-most vertices
          if (front > 0.65 && size >= 100) {
            ctx.fillStyle = "rgba(255, 255, 255, 0.95)";
            ctx.beginPath();
            ctx.arc(o.x - r * 0.28, o.y - r * 0.28, Math.max(0.5, 0.35 * sRatio), 0, Math.PI * 2);
            ctx.fill();
          }
        }
      });

      frame = requestAnimationFrame(draw);
    };

    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [size]);

  return <canvas ref={canvasRef} style={{ width: size, height: size }} aria-hidden className="block" />;
}
