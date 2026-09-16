import * as THREE from 'three';

/**
 * §30: the monitor runs a Lorenz attractor as a screensaver.
 *
 * This is the real system — dx/dt = σ(y−x), dy/dt = x(ρ−z)−y, dz/dt = xy−βz, integrated with
 * RK4 — not a decorative curve. The trajectory is kept in a ring buffer and drawn as a handful
 * of constant-alpha bands rather than a few thousand individually stroked segments, which is
 * what keeps a full repaint cheap enough to run at 30 Hz.
 *
 * The canvas only repaints when the screen is actually on camera (§26/§27).
 */

const SIGMA = 10;
const RHO = 28;
const BETA = 8 / 3;

const W = 768;
const H = 432;
// Long enough to hold roughly 29 time units — the full two-lobed figure, not one loop.
const TRAIL = 9000;
const BANDS = 10;
/** Repaints per second. The attractor drifts slowly; more than this is invisible. */
const HZ = 30;

function derivative(x: number, y: number, z: number, out: [number, number, number]) {
  out[0] = SIGMA * (y - x);
  out[1] = x * (RHO - z) - y;
  out[2] = x * y - BETA * z;
}

export function createLorenzScreen() {
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d', { alpha: false })!;
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;

  // Trajectory ring buffer.
  const xs = new Float32Array(TRAIL);
  const ys = new Float32Array(TRAIL);
  const zs = new Float32Array(TRAIL);
  let head = 0;
  let filled = 0;
  let state: [number, number, number] = [0.9, 1.2, 22.0];

  const k1: [number, number, number] = [0, 0, 0];
  const k2: [number, number, number] = [0, 0, 0];
  const k3: [number, number, number] = [0, 0, 0];
  const k4: [number, number, number] = [0, 0, 0];

  function integrate(h: number) {
    const [x, y, z] = state;
    derivative(x, y, z, k1);
    derivative(x + (h / 2) * k1[0], y + (h / 2) * k1[1], z + (h / 2) * k1[2], k2);
    derivative(x + (h / 2) * k2[0], y + (h / 2) * k2[1], z + (h / 2) * k2[2], k3);
    derivative(x + h * k3[0], y + h * k3[1], z + h * k3[2], k4);
    state = [
      x + (h / 6) * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]),
      y + (h / 6) * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]),
      z + (h / 6) * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2]),
    ];
    xs[head] = state[0];
    ys[head] = state[1];
    zs[head] = state[2];
    head = (head + 1) % TRAIL;
    if (filled < TRAIL) filled++;
  }

  // Seed the trail so the first visible frame already shows the full attractor.
  for (let i = 0; i < TRAIL; i++) integrate(0.0035);

  let spin = 0;
  let orbit = 0;
  let clock = 0;
  let warmth = 0;

  function paint(time: number, activity: number) {
    // Slow orbit around the attractor's vertical axis.
    const cos = Math.cos(spin);
    const sin = Math.sin(spin);
    const scale = H / 52;
    const cx = W / 2;
    const cy = H / 2;

    const bg = ctx.createRadialGradient(cx, cy - H * 0.05, 0, cx, cy, W * 0.62);
    bg.addColorStop(0, '#0d141b');
    bg.addColorStop(1, '#04070a');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);

    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    const perBand = Math.floor(filled / BANDS);
    // Oldest band first so newer trail draws over it.
    for (let b = 0; b < BANDS; b++) {
      const age = b / (BANDS - 1);
      ctx.beginPath();
      let started = false;
      for (let j = 0; j <= perBand; j++) {
        const idx = (head - filled + b * perBand + j + TRAIL * 2) % TRAIL;
        const x = xs[idx];
        const y = ys[idx];
        const z = zs[idx];
        // Rotate about z, then drop to the screen plane with a little perspective from depth.
        const rx = x * cos - y * sin;
        const ry = x * sin + y * cos;
        const depth = 1 + ry / 90;
        const px = cx + rx * scale * depth;
        const py = cy - (z - 27) * scale * depth;
        started ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
        started = true;
      }
      const alpha = 0.06 + age * 0.62;
      const warmMix = warmth * age;
      const r = Math.round(138 + warmMix * 110);
      const g = Math.round(186 - warmMix * 40);
      const bl = Math.round(226 - warmMix * 110);
      ctx.strokeStyle = `rgba(${r},${g},${bl},${alpha})`;
      ctx.lineWidth = 0.9 + age * 1.5;
      ctx.stroke();
    }

    // Leading point, with a soft glow.
    const hx = (head - 1 + TRAIL) % TRAIL;
    const hrx = xs[hx] * cos - ys[hx] * sin;
    const hry = xs[hx] * sin + ys[hx] * cos;
    const hd = 1 + hry / 90;
    const hpx = cx + hrx * scale * hd;
    const hpy = cy - (zs[hx] - 27) * scale * hd;
    const glow = ctx.createRadialGradient(hpx, hpy, 0, hpx, hpy, 26);
    glow.addColorStop(0, 'rgba(226,240,255,0.55)');
    glow.addColorStop(1, 'rgba(226,240,255,0)');
    ctx.fillStyle = glow;
    ctx.fillRect(hpx - 26, hpy - 26, 52, 52);
    ctx.fillStyle = 'rgba(245,250,255,0.95)';
    ctx.beginPath();
    ctx.arc(hpx, hpy, 1.9, 0, Math.PI * 2);
    ctx.fill();

    // Corner readout: the parameters actually driving the system.
    ctx.fillStyle = 'rgba(150,172,190,0.34)';
    ctx.font = '400 13px "IBM Plex Sans", ui-monospace, monospace';
    ctx.textAlign = 'left';
    ctx.fillText(`σ ${SIGMA}   ρ ${RHO}   β 8/3`, 22, H - 22);
    ctx.textAlign = 'right';
    ctx.fillText(`t ${time.toFixed(1)}`, W - 22, H - 22);

    texture.needsUpdate = true;
    void activity;
  }

  return {
    texture,
    /**
     * `visible` gates every bit of work: when the screen is off camera the attractor stops
     * integrating and stops repainting, and resumes seamlessly when it comes back.
     */
    update(dt: number, time: number, visible: boolean, activity: number) {
      if (!visible) return;
      clock += dt;
      if (clock < 1 / HZ) return;
      const stepped = clock;
      clock = 0;
      // Advance by wall-clock time so the motion is frame-rate independent.
      const substeps = Math.min(14, Math.max(4, Math.round(stepped * 340)));
      for (let i = 0; i < substeps; i++) integrate(0.0032);
      // Oscillate rather than spin: a full rotation would periodically show the attractor
      // edge-on, where the figure stops being readable.
      orbit += stepped * 0.055;
      spin = Math.sin(orbit) * 0.62;
      // Examining a project warms the trace very slightly: a small reaction, not a mode change.
      warmth += (activity - warmth) * Math.min(1, stepped * 2);
      paint(time, activity);
    },
  };
}
