import { useEffect, useRef } from "react";
import type { VoicePhase } from "@/features/home/voice";

/**
 * The IRIS Sphere: A refined, black and deep graphite kinetic intelligence core.
 * Features a dark carbon-graphite body, precision geometric web links,
 * rotating concentric star geometry, and specular obsidian nodes.
 *
 * Preserves all underlying rotational kinetics, mathematical geometry,
 * phase states (idle, listening, thinking, speaking), and audio reactivity.
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

/** Precision dark graphite/carbon bead with specular micro-sheen. */
function createNodeSprite(px: number): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = c.height = px;
  const g = c.getContext("2d")!;
  const r = px / 2;

  // Soft subtle ambient occlusion
  const shadow = g.createRadialGradient(r, r + 0.5, r * 0.2, r, r + 0.5, r * 0.85);
  shadow.addColorStop(0, "rgba(0, 0, 0, 0.45)");
  shadow.addColorStop(1, "rgba(0, 0, 0, 0)");
  g.fillStyle = shadow;
  g.fillRect(0, 0, px, px);

  // Precision obsidian / carbon bead gradient
  const bead = g.createRadialGradient(r - r * 0.28, r - r * 0.28, 0, r, r, r * 0.65);
  bead.addColorStop(0, "#475569"); // slate-graphite specular highlight
  bead.addColorStop(0.35, "#1e293b"); // deep graphite body
  bead.addColorStop(0.85, "#0f172a"); // carbon rim
  bead.addColorStop(1, "#020617"); // obsidian edge
  g.beginPath();
  g.arc(r, r, r * 0.62, 0, Math.PI * 2);
  g.fillStyle = bead;
  g.fill();

  // Subtle specular micro-dot
  g.beginPath();
  g.arc(r - r * 0.22, r - r * 0.22, r * 0.1, 0, Math.PI * 2);
  g.fillStyle = "rgba(255, 255, 255, 0.5)";
  g.fill();

  return c;
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
    const sprite = createNodeSprite(32);
    const projected = pts.map(() => ({ x: 0, y: 0, z: 0, s: 1 }));

    const c = size / 2;
    let rotY = 0;
    let rotX = 0.35;
    let spin = 0;
    let shown = 0; // smoothed reactivity level
    let last = performance.now();
    let frame = 0;

    const draw = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      const p = phaseRef.current;
      const t = now / 1000;

      // Preserved responsiveness logic
      let target = 0.06;
      if (p === "listening") target = Math.min(1, levelRef.current());
      else if (p === "paused") target = 0.04;
      else if (p === "speaking")
        target = 0.32 + 0.25 * Math.abs(Math.sin(t * 7.3)) * (0.6 + 0.4 * Math.sin(t * 2.1 + 1.3));
      else if (p === "thinking" || p === "transcribing") target = 0.2 + 0.08 * Math.sin(t * 5);
      shown += (target - shown) * Math.min(1, dt * 10);

      const speed = reduceMotion
        ? 0
        : p === "thinking" || p === "transcribing"
        ? 1.3
        : 0.35 + shown * 0.55;
      rotY += speed * dt;
      rotX = 0.35 + Math.sin(t * 0.4) * 0.14;
      spin += (reduceMotion ? 0 : speed * 0.55) * dt;

      const R = size * 0.34 * (1 + shown * 0.08);
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

      ctx.clearRect(0, 0, size, size);
      ctx.globalCompositeOperation = "source-over";

      // 1. Base dark graphite sphere body (gives physical volume and depth)
      const bodyGrad = ctx.createRadialGradient(
        c - R * 0.25,
        c - R * 0.25,
        R * 0.05,
        c,
        c,
        R * 1.02,
      );
      bodyGrad.addColorStop(0, "#232b35"); // dark matte graphite specular highlight
      bodyGrad.addColorStop(0.45, "#151a21"); // obsidian charcoal body
      bodyGrad.addColorStop(0.88, "#0c0f14"); // deep carbon
      bodyGrad.addColorStop(1, "rgba(10, 13, 17, 0.96)"); // perimeter
      ctx.beginPath();
      ctx.arc(c, c, R, 0, Math.PI * 2);
      ctx.fillStyle = bodyGrad;
      ctx.fill();

      // Precision rim highlight (subtle depth definition against daylight ground)
      ctx.lineWidth = 1;
      ctx.strokeStyle = shown > 0.2 ? "rgba(31, 100, 95, 0.4)" : "rgba(255, 255, 255, 0.1)";
      ctx.stroke();

      // 2. The web: precision dark graphite hairline links
      for (const [a, b] of links) {
        const pa = projected[a], pb = projected[b];
        const depth = (pa.z + pb.z) / 2; // -1 (back) .. 1 (front)
        ctx.beginPath();
        ctx.moveTo(pa.x, pa.y);
        ctx.lineTo(pb.x, pb.y);

        if (depth < -0.25) {
          // Subtle back links
          ctx.lineWidth = 0.6;
          ctx.strokeStyle = `rgba(100, 116, 139, ${(0.16 + 0.1 * depth).toFixed(3)})`;
        } else {
          // Front links: crisp charcoal
          const frontAlpha = 0.32 + 0.45 * ((depth + 1) / 2);
          ctx.lineWidth = 0.85;
          if (shown > 0.18) {
            ctx.strokeStyle = `rgba(31, 100, 95, ${(frontAlpha * (0.6 + shown * 0.4)).toFixed(3)})`;
          } else {
            ctx.strokeStyle = `rgba(30, 41, 59, ${frontAlpha.toFixed(3)})`;
          }
        }
        ctx.stroke();
      }

      // 3. Inner 12-point star & hexagon, turning against the sphere
      const star = (
        radius: number,
        inner: number,
        points: number,
        rot: number,
        w: number,
        color: string,
      ) => {
        ctx.lineWidth = w;
        ctx.strokeStyle = color;
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

      const starAlpha = 0.22 + shown * 0.32;
      star(
        R * 0.58,
        R * 0.38,
        12,
        -spin,
        0.85,
        `rgba(71, 85, 105, ${starAlpha.toFixed(3)})`,
      );
      star(
        R * 0.2,
        R * 0.2,
        3,
        spin * 1.5,
        1.0,
        shown > 0.2
          ? `rgba(31, 100, 95, ${(starAlpha * 1.1).toFixed(3)})`
          : `rgba(51, 65, 85, ${starAlpha.toFixed(3)})`,
      );

      // 4. Nodes: depth-sorted obsidian beads
      const sortedNodes = [...projected].sort((a, b) => a.z - b.z);
      sortedNodes.forEach((o) => {
        const front = (o.z + 1) / 2;
        const s = (2.2 + front * 3.8) * o.s * (1 + shown * 0.1);
        ctx.globalAlpha = 0.35 + front * 0.65;
        ctx.drawImage(sprite, o.x - s, o.y - s, s * 2, s * 2);
      });

      // 5. Central Mechanical Core
      const coreR = R * (0.16 + shown * 0.06);
      const coreGrad = ctx.createRadialGradient(c - 1, c - 1, 0, c, c, coreR);
      coreGrad.addColorStop(0, "#334155");
      coreGrad.addColorStop(0.65, "#0f172a");
      coreGrad.addColorStop(1, "#020617");
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(c, c, coreR, 0, Math.PI * 2);
      ctx.fillStyle = coreGrad;
      ctx.fill();
      ctx.lineWidth = 1;
      ctx.strokeStyle = shown > 0.2 ? "rgba(31, 100, 95, 0.7)" : "rgba(255, 255, 255, 0.15)";
      ctx.stroke();

      frame = requestAnimationFrame(draw);
    };

    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [size]);

  return <canvas ref={canvasRef} style={{ width: size, height: size }} aria-hidden className="block" />;
}
