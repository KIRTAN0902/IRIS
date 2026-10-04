import { useEffect, useRef } from "react";
import type { VoicePhase } from "@/features/home/voice";

/**
 * The IRIS sphere: a glowing, rotating network of nodes (the logo's outer web)
 * around a turning 12-point star and a bright core. It breathes with the
 * user's voice while listening, spins while thinking and pulses while speaking.
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

/** Evenly spread points on a unit sphere. */
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

/** A soft white glow, drawn once and stamped for every node. */
function glowSprite(px: number): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = c.height = px;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(px / 2, px / 2, 0, px / 2, px / 2, px / 2);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.18, "rgba(255,255,255,0.85)");
  grad.addColorStop(0.45, "rgba(220,230,255,0.22)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, px, px);
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
    const sprite = glowSprite(64);
    const projected = pts.map(() => ({ x: 0, y: 0, z: 0, s: 1 }));

    const c = size / 2;
    let rotY = 0;
    let rotX = 0.35;
    let spin = 0;
    let shown = 0; // smoothed level actually drawn
    let last = performance.now();
    let frame = 0;

    const draw = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      const p = phaseRef.current;
      const t = now / 1000;

      // How lively the sphere is: real mic level while listening, a speech-like
      // pulse while speaking, a slow shimmer while thinking.
      let target = 0.08;
      if (p === "listening") target = Math.min(1, levelRef.current());
      else if (p === "speaking")
        target = 0.35 + 0.3 * Math.abs(Math.sin(t * 7.3)) * (0.6 + 0.4 * Math.sin(t * 2.1 + 1.3));
      else if (p === "thinking" || p === "transcribing") target = 0.22 + 0.1 * Math.sin(t * 5);
      shown += (target - shown) * Math.min(1, dt * 10);

      const speed = reduceMotion ? 0 : p === "thinking" || p === "transcribing" ? 1.4 : 0.35 + shown * 0.6;
      rotY += speed * dt;
      rotX = 0.35 + Math.sin(t * 0.4) * 0.15;
      spin += (reduceMotion ? 0 : speed * 0.6) * dt;

      const R = size * 0.34 * (1 + shown * 0.14);
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
      ctx.globalCompositeOperation = "lighter";

      // Halo behind everything.
      const halo = ctx.createRadialGradient(c, c, R * 0.2, c, c, R * 1.5);
      halo.addColorStop(0, `rgba(255,255,255,${0.07 + shown * 0.08})`);
      halo.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = halo;
      ctx.fillRect(0, 0, size, size);

      // The web: a wide faint pass for glow, then a crisp pass.
      for (const [width, boost] of [
        [3.2, 0.12],
        [0.9, 0.55],
      ] as const) {
        ctx.lineWidth = width;
        for (const [a, b] of links) {
          const pa = projected[a], pb = projected[b];
          const depth = (pa.z + pb.z) / 2; // -1 (back) .. 1 (front)
          const alpha = boost * (0.25 + 0.75 * ((depth + 1) / 2)) * (0.7 + shown * 0.6);
          ctx.strokeStyle = `rgba(255,255,255,${alpha.toFixed(3)})`;
          ctx.beginPath();
          ctx.moveTo(pa.x, pa.y);
          ctx.lineTo(pb.x, pb.y);
          ctx.stroke();
        }
      }

      // Inner 12-point star and hexagon, turning against the sphere.
      const star = (radius: number, inner: number, points: number, rot: number, alpha: number, w: number) => {
        ctx.lineWidth = w;
        ctx.strokeStyle = `rgba(255,255,255,${alpha.toFixed(3)})`;
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
      const glowA = 0.5 + shown * 0.5;
      star(R * 0.62, R * 0.42, 12, -spin, 0.1 * glowA, 4);
      star(R * 0.62, R * 0.42, 12, -spin, 0.55 * glowA, 1.1);
      star(R * 0.2, R * 0.2, 3, spin * 1.5, 0.7 * glowA, 1.4); // hexagon (6 equal points)

      // Nodes: bigger and brighter at the front.
      projected.forEach((o) => {
        const front = (o.z + 1) / 2;
        const s = (3 + front * 7) * o.s * (1 + shown * 0.4);
        ctx.globalAlpha = 0.25 + front * 0.75;
        ctx.drawImage(sprite, o.x - s, o.y - s, s * 2, s * 2);
      });

      // Core.
      const core = R * (0.28 + shown * 0.22);
      ctx.globalAlpha = 0.85;
      ctx.drawImage(sprite, c - core, c - core, core * 2, core * 2);
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";

      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [size]);

  return <canvas ref={canvasRef} style={{ width: size, height: size }} aria-hidden className="block" />;
}
