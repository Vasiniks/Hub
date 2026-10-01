/**
 * The monitor is already on.
 *
 * While the room loads, the loader shows a live trace of the same Lorenz system that runs
 * on the desk monitor once inside (see `src/scene/lorenz.ts`: σ = 10, ρ = 28, β = 8/3,
 * integrated with RK4). It is watchable from the first frame, and the visitor can tilt the
 * projection by moving the pointer over the loader — a small reaction, not a game, and it
 * never affects loading.
 *
 * Budget discipline (the loader's whole budget is what the GPU and network are not using):
 * - Canvas2D only. A second WebGL context during `view.warmUp` is forbidden; this is one
 *   small 2D canvas, one polyline stroke plus a head dot per frame, at ~24 Hz.
 * - The trail buffer is small (1600 points) and seeded synchronously in microseconds, so the
 *   first painted frame already shows the full two-lobed figure.
 * - `stop()` cancels the loop and removes the listener synchronously. It is called from
 *   `hide()`/`fail()` before the reveal, so the activity can never hold the reveal hostage
 *   or burn CPU behind the room.
 *
 * Honesty: this module never reports progress. The bar and the stage label in `loading.ts`
 * stay purely stage-driven (`loader.advance`); the caption here is static text.
 *
 * Accessibility: the canvas is decorative (`aria-hidden` in markup) — screen readers hear
 * only the honest `role="status"` label. The trace is watch-only with an optional
 * pointer enhancement, so keyboard users lose nothing and focus is never trapped. Under
 * `prefers-reduced-motion` exactly one static frame is painted and no loop ever starts.
 */

const SIGMA = 10;
const RHO = 28;
const BETA = 8 / 3;

/** Internal pixels. Small on purpose: one stroke at this size costs well under a millisecond. */
const W = 384;
const H = 192;
const TRAIL = 1600;
/** Repaints per second. The attractor drifts slowly; more than this is invisible. */
const HZ = 24;

export function createLoadingTrace(canvas: HTMLCanvasElement, host: HTMLElement) {
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d', { alpha: false })!;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Trajectory ring buffer — the same RK4 system as the monitor screen.
  const xs = new Float32Array(TRAIL);
  const ys = new Float32Array(TRAIL);
  const zs = new Float32Array(TRAIL);
  let head = 0;
  let state: [number, number, number] = [0.9, 1.2, 22.0];

  function integrate(h: number) {
    const [x, y, z] = state;
    const k1x = SIGMA * (y - x);
    const k1y = x * (RHO - z) - y;
    const k1z = x * y - BETA * z;
    const mx = x + (h / 2) * k1x;
    const my = y + (h / 2) * k1y;
    const mz = z + (h / 2) * k1z;
    const k2x = SIGMA * (my - mx);
    const k2y = mx * (RHO - mz) - my;
    const k2z = mx * my - BETA * mz;
    const nx = x + (h / 2) * k2x;
    const ny = y + (h / 2) * k2y;
    const nz = z + (h / 2) * k2z;
    const k3x = SIGMA * (ny - nx);
    const k3y = nx * (RHO - nz) - ny;
    const k3z = nx * ny - BETA * nz;
    const ox = x + h * k3x;
    const oy = y + h * k3y;
    const oz = z + h * k3z;
    const k4x = SIGMA * (oy - ox);
    const k4y = ox * (RHO - oz) - oy;
    const k4z = ox * oy - BETA * oz;
    state = [
      x + (h / 6) * (k1x + 2 * k2x + 2 * k3x + k4x),
      y + (h / 6) * (k1y + 2 * k2y + 2 * k3y + k4y),
      z + (h / 6) * (k1z + 2 * k2z + 2 * k3z + k4z),
    ];
    xs[head] = state[0];
    ys[head] = state[1];
    zs[head] = state[2];
    head = (head + 1) % TRAIL;
  }

  // Seed the trail so the first visible frame already shows the full figure.
  for (let i = 0; i < TRAIL; i++) integrate(0.0035);

  // Pointer tilt: an offset around the slow oscillation, eased toward the pointer.
  let tilt = 0;
  let tiltTarget = 0;
  function onPointerMove(e: PointerEvent) {
    const r = host.getBoundingClientRect();
    if (r.width <= 0) return;
    tiltTarget = ((e.clientX - r.left) / r.width - 0.5) * 0.7;
  }

  let spin = 0;
  let orbit = 0;

  function paint() {
    const cos = Math.cos(spin + tilt);
    const sin = Math.sin(spin + tilt);
    const scale = H / 56;
    const cx = W / 2;
    const cy = H / 2 + 6;

    ctx.fillStyle = '#0f1216';
    ctx.fillRect(0, 0, W, H);

    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.beginPath();
    for (let j = 0; j < TRAIL; j++) {
      const idx = (head + j) % TRAIL;
      const rx = xs[idx] * cos - ys[idx] * sin;
      const ry = xs[idx] * sin + ys[idx] * cos;
      const depth = 1 + ry / 90;
      const px = cx + rx * scale * depth;
      const py = cy - (zs[idx] - 27) * scale * depth;
      if (j === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.strokeStyle = 'rgba(138,186,226,0.78)';
    ctx.lineWidth = 1.1;
    ctx.stroke();

    // Leading point.
    const hx = (head - 1 + TRAIL) % TRAIL;
    const hrx = xs[hx] * cos - ys[hx] * sin;
    const hry = xs[hx] * sin + ys[hx] * cos;
    const hd = 1 + hry / 90;
    ctx.fillStyle = 'rgba(240,246,252,0.95)';
    ctx.beginPath();
    ctx.arc(cx + hrx * scale * hd, cy - (zs[hx] - 27) * scale * hd, 2, 0, Math.PI * 2);
    ctx.fill();
  }

  // Reduced motion: one full static figure, painted once, no loop, no listener.
  if (reduced) {
    paint();
    return { stop() {} };
  }

  host.addEventListener('pointermove', onPointerMove);
  let raf = 0;
  let last = performance.now();
  let stopped = false;

  function frame(now: number) {
    if (stopped) return;
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    // Advance by wall-clock time so the motion is frame-rate independent: a fixed step,
    // more of them when the main thread was busy loading. Same h as the monitor's drift, so
    // the handoff reads as continuous. Capped — this must never do real work per frame.
    const steps = Math.min(30, Math.max(6, Math.round(dt * HZ * 6)));
    for (let i = 0; i < steps; i++) integrate(0.0032);
    orbit += dt * 0.055;
    spin = Math.sin(orbit) * 0.62;
    tilt += (tiltTarget - tilt) * Math.min(1, dt * 4);
    paint();
    // Pace the loop instead of free-running: the figure needs no more than this.
    window.setTimeout(() => {
      if (!stopped) raf = requestAnimationFrame(frame);
    }, 1000 / HZ);
  }
  raf = requestAnimationFrame(frame);

  let done = false;
  return {
    stop() {
      if (done) return;
      done = true;
      stopped = true;
      cancelAnimationFrame(raf);
      host.removeEventListener('pointermove', onPointerMove);
    },
  };
}
