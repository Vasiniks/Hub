/**
 * The loading figure itself: the desk monitor's Lorenz system plus the points the visitor drops
 * into it. Pure simulation and Canvas2D drawing, no DOM — it runs inside the loading worker
 * (`loadingTrace.worker.ts`) and, where OffscreenCanvas is missing, on the page itself.
 *
 * Same system as `src/scene/lorenz.ts`: σ = 10, ρ = 28, β = 8/3, RK4 at h = 0.0032, ~340 steps
 * a second (the monitor's own rate), the same slow oscillating projection and blue trace.
 */

const SIGMA = 10;
const RHO = 28;
const BETA = 8 / 3;
const H_STEP = 0.0032;
/** The monitor integrates ~340 steps per second (lorenz.ts `stepped * 340`). */
const STEPS_PER_SECOND = 340;

import { TOY_H, TOY_TURN, TOY_W } from './lorenzToySize';

/** ~13 time units of history: enough loops to read as the whole figure, as on the monitor. */
const TRAIL = 4000;
const BANDS = 4;
/** Visitor-dropped points: a short trail each, oldest dropped past the cap. */
const SEED_TRAIL = 300;
const MAX_SEEDS = 6;

type Ctx2D = CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;
type Vec3 = [number, number, number];

interface Seed {
  x: Float32Array;
  y: Float32Array;
  z: Float32Array;
  head: number;
  filled: number;
  s: Vec3;
}

function rk4(s: Vec3, h: number) {
  const [x, y, z] = s;
  const k1x = SIGMA * (y - x), k1y = x * (RHO - z) - y, k1z = x * y - BETA * z;
  const ax = x + (h / 2) * k1x, ay = y + (h / 2) * k1y, az = z + (h / 2) * k1z;
  const k2x = SIGMA * (ay - ax), k2y = ax * (RHO - az) - ay, k2z = ax * ay - BETA * az;
  const bx = x + (h / 2) * k2x, by = y + (h / 2) * k2y, bz = z + (h / 2) * k2z;
  const k3x = SIGMA * (by - bx), k3y = bx * (RHO - bz) - by, k3z = bx * by - BETA * bz;
  const cx = x + h * k3x, cy = y + h * k3y, cz = z + h * k3z;
  const k4x = SIGMA * (cy - cx), k4y = cx * (RHO - cz) - cy, k4z = cx * cy - BETA * cz;
  s[0] = x + (h / 6) * (k1x + 2 * k2x + 2 * k3x + k4x);
  s[1] = y + (h / 6) * (k1y + 2 * k2y + 2 * k3y + k4y);
  s[2] = z + (h / 6) * (k1z + 2 * k2z + 2 * k3z + k4z);
}

export function createLorenzToy(ctx: Ctx2D, dpr: number, reduced: boolean) {
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const W = TOY_W;
  const H = TOY_H;

  // Projection: rotate about z, drop to the screen plane with a little depth — as the monitor.
  const scale = H / 50;
  const cx = W / 2;
  const cy = H / 2 + 4;
  let cos = 1;
  let sin = 0;
  const px = (x: number, y: number) => cx + (x * cos - y * sin) * scale * (1 + (x * sin + y * cos) / 90);
  const py = (x: number, y: number, z: number) => cy - (z - 27) * scale * (1 + (x * sin + y * cos) / 90);

  // The monitor's own trajectory, seeded so the first frame already shows both wings.
  const xs = new Float32Array(TRAIL);
  const ys = new Float32Array(TRAIL);
  const zs = new Float32Array(TRAIL);
  const state: Vec3 = [0.9, 1.2, 22.0];
  let head = 0;
  function step() {
    rk4(state, H_STEP);
    xs[head] = state[0];
    ys[head] = state[1];
    zs[head] = state[2];
    head = (head + 1) % TRAIL;
  }
  for (let i = 0; i < TRAIL; i++) step();

  const seeds: Seed[] = [];
  function stepSeed(sd: Seed) {
    rk4(sd.s, H_STEP);
    sd.x[sd.head] = sd.s[0];
    sd.y[sd.head] = sd.s[1];
    sd.z[sd.head] = sd.s[2];
    sd.head = (sd.head + 1) % SEED_TRAIL;
    if (sd.filled < SEED_TRAIL) sd.filled++;
  }

  // The screen: the monitor's dark glass, built once.
  const glass = ctx.createRadialGradient(cx, cy - H * 0.05, 0, cx, cy, W * 0.62);
  glass.addColorStop(0, '#0d141b');
  glass.addColorStop(1, '#04070a');

  function strokeRing(
    ax: Float32Array, ay: Float32Array, az: Float32Array,
    size: number, filled: number, hd: number, bands: number,
    color: (age: number) => string, width: (age: number) => number,
  ) {
    const per = Math.floor(filled / bands);
    if (per < 1) return;
    for (let b = 0; b < bands; b++) {
      const age = bands === 1 ? 1 : b / (bands - 1);
      ctx.beginPath();
      // Each band reaches one point into the next so they join; the newest stops at the head,
      // or it would wrap round and draw a chord back to the oldest point.
      const last = Math.min(per, filled - 1 - b * per);
      for (let j = 0; j <= last; j++) {
        const i = (hd - filled + b * per + j + size * 2) % size;
        const X = ax[i], Y = ay[i];
        if (j === 0) ctx.moveTo(px(X, Y), py(X, Y, az[i]));
        else ctx.lineTo(px(X, Y), py(X, Y, az[i]));
      }
      ctx.strokeStyle = color(age);
      ctx.lineWidth = width(age);
      ctx.stroke();
    }
  }

  function dot(x: number, y: number, z: number, r: number, fill: string) {
    ctx.fillStyle = fill;
    ctx.beginPath();
    ctx.arc(px(x, y), py(x, y, z), r, 0, Math.PI * 2);
    ctx.fill();
  }

  // Slow oscillation (never a full turn, as on the monitor) plus the visitor's turn.
  let orbit = 0;
  let turn = 0;
  let turnTarget = 0;
  const angle = () => Math.sin(orbit) * 0.62 + turn;

  function paint() {
    const a = angle();
    cos = Math.cos(a);
    sin = Math.sin(a);
    ctx.fillStyle = glass;
    ctx.fillRect(0, 0, W, H);
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    strokeRing(xs, ys, zs, TRAIL, TRAIL, head, BANDS,
      (t) => `rgba(138,186,226,${(0.1 + t * 0.62).toFixed(3)})`, (t) => 0.8 + t * 0.6);
    const h = (head - 1 + TRAIL) % TRAIL;
    dot(xs[h], ys[h], zs[h], 1.9, 'rgba(245,250,255,0.95)');

    // The visitor's points, in the room's signal orange, drawn over the monitor's trace.
    for (const sd of seeds) {
      strokeRing(sd.x, sd.y, sd.z, SEED_TRAIL, sd.filled, sd.head, 3,
        (t) => `rgba(255,122,26,${(0.18 + t * 0.7).toFixed(3)})`, (t) => 0.9 + t * 0.8);
      const sh = (sd.head - 1 + SEED_TRAIL) % SEED_TRAIL;
      dot(sd.x[sh], sd.y[sh], sd.z[sh], 2.4, 'rgba(255,196,150,1)');
    }
  }

  return {
    paint,
    /** Advance by wall-clock seconds and repaint. Capped: a stall never becomes a catch-up burst. */
    tick(dt: number) {
      dt = Math.min(0.1, dt);
      const n = Math.round(dt * STEPS_PER_SECOND);
      for (let i = 0; i < n; i++) step();
      for (const sd of seeds) for (let i = 0; i < n; i++) stepSeed(sd);
      orbit += dt * 0.055;
      turn += (turnTarget - turn) * Math.min(1, dt * 4);
      paint();
    },
    /**
     * Start a point at (x, y) in drawing units, on the plane facing the viewer; `null` drops it
     * in from above. Under reduced motion the whole capture is integrated and drawn at once.
     */
    drop(at: [number, number] | null) {
      const [qx, qy] = at ?? [W * (0.3 + Math.random() * 0.4), H * 0.12];
      // Invert the projection at depth 0: screen x is the rotated x, screen y is z.
      const a = angle();
      const rx = (qx - cx) / scale;
      const z = 27 - (qy - cy) / scale;
      // A hair off the z-axis, so a point dropped dead centre still leaves the origin's pull.
      const jitter = (Math.random() - 0.5) * 0.6;
      const s: Vec3 = [rx * Math.cos(a) + jitter, -rx * Math.sin(a) + jitter, z];
      const sd: Seed = {
        x: new Float32Array(SEED_TRAIL), y: new Float32Array(SEED_TRAIL), z: new Float32Array(SEED_TRAIL),
        head: 1, filled: 1, s,
      };
      sd.x[0] = s[0];
      sd.y[0] = s[1];
      sd.z[0] = s[2];
      seeds.push(sd);
      if (seeds.length > MAX_SEEDS) seeds.shift();
      if (reduced) {
        for (let i = 1; i < SEED_TRAIL; i++) stepSeed(sd);
        paint();
      }
    },
    /** Where the visitor wants the figure turned, in radians (clamped to ±TOY_TURN). */
    turnTo(target: number) {
      turnTarget = Math.max(-TOY_TURN, Math.min(TOY_TURN, target));
      if (reduced) {
        turn = turnTarget;
        paint();
      }
    },
  };
}

export type LorenzToy = ReturnType<typeof createLorenzToy>;
