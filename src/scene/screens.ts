import * as THREE from 'three';

/**
 * Monitor contents are drawn to canvases. This is the seam where the future
 * desktop (windows, apps, files) will live; for now it paints a believable
 * workstation and reacts to what the visitor is examining.
 */
export interface ScreenState {
  focusTitle: string | null;
  time: number;
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}

function paintWindow(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, title: string, active: boolean) {
  ctx.save();
  ctx.shadowColor = 'rgba(0,0,0,0.45)';
  ctx.shadowBlur = 28;
  ctx.shadowOffsetY = 10;
  roundRect(ctx, x, y, w, h, 10);
  ctx.fillStyle = '#1b1f24';
  ctx.fill();
  ctx.restore();
  roundRect(ctx, x, y, w, 34, 10);
  ctx.fillStyle = active ? '#2a3038' : '#23282e';
  ctx.fill();
  ctx.fillRect(x, y + 24, w, 10);
  ['#ff5f57', '#febc2e', '#28c840'].forEach((c, i) => {
    ctx.beginPath();
    ctx.arc(x + 18 + i * 18, y + 17, 5, 0, Math.PI * 2);
    ctx.fillStyle = active ? c : '#4a5058';
    ctx.fill();
  });
  ctx.fillStyle = active ? '#d9dee4' : '#8b939c';
  ctx.font = '500 15px "IBM Plex Sans", system-ui, sans-serif';
  ctx.fillText(title, x + 76, y + 22);
}

function paintCode(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, lines: number, seed: number) {
  const palette = ['#7c8a99', '#c3a86b', '#8fb3c9', '#9cc39a', '#b48ead', '#d0d4d9'];
  let s = seed;
  const r = () => ((s = (s * 9301 + 49297) % 233280) / 233280);
  for (let i = 0; i < lines; i++) {
    const indent = Math.floor(r() * 4) * 18;
    let cx = x + 36 + indent;
    ctx.fillStyle = '#4a525c';
    ctx.fillRect(x + 8, y + i * 20 + 6, 14, 6);
    const tokens = 1 + Math.floor(r() * 5);
    for (let t = 0; t < tokens && cx < x + w - 40; t++) {
      const tw = 20 + r() * 90;
      ctx.fillStyle = palette[Math.floor(r() * palette.length)];
      ctx.globalAlpha = 0.85;
      ctx.fillRect(cx, y + i * 20 + 5, tw, 8);
      cx += tw + 8;
    }
    ctx.globalAlpha = 1;
  }
}

export function createScreens() {
  const mainCanvas = document.createElement('canvas');
  mainCanvas.width = 1600;
  mainCanvas.height = 900;
  const sideCanvas = document.createElement('canvas');
  sideCanvas.width = 1280;
  sideCanvas.height = 726;

  const mainTex = new THREE.CanvasTexture(mainCanvas);
  const sideTex = new THREE.CanvasTexture(sideCanvas);
  for (const t of [mainTex, sideTex]) {
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = 8;
  }

  let lastFocus: string | null | undefined;

  function paintMain(state: ScreenState) {
    const ctx = mainCanvas.getContext('2d')!;
    const { width: W, height: H } = mainCanvas;
    const g = ctx.createLinearGradient(0, 0, W, H);
    g.addColorStop(0, '#20303b');
    g.addColorStop(1, '#0e151b');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(10,12,15,0.7)';
    ctx.fillRect(0, 0, W, 30);

    const focused = state.focusTitle !== null;
    paintWindow(ctx, 120, 90, 900, 640, 'controller.ts', !focused);
    paintCode(ctx, 120, 140, 900, 27, 11);
    paintWindow(ctx, 1060, 150, 440, 300, 'notes', false);
    ctx.fillStyle = '#6f7882';
    for (let i = 0; i < 8; i++) ctx.fillRect(1084, 206 + i * 26, 160 + ((i * 53) % 200), 7);

    if (focused) {
      paintWindow(ctx, 560, 300, 820, 460, state.focusTitle!, true);
      ctx.fillStyle = '#2c333b';
      ctx.fillRect(590, 360, 360, 220);
      ctx.strokeStyle = '#ff7a1a';
      ctx.lineWidth = 3;
      ctx.beginPath();
      for (let i = 0; i <= 60; i++) {
        const px = 600 + i * 5.7;
        const py = 470 - Math.sin(i * 0.22) * 60 * Math.exp(-i * 0.03);
        i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
      }
      ctx.stroke();
      ctx.fillStyle = '#9aa3ad';
      for (let i = 0; i < 9; i++) ctx.fillRect(980, 370 + i * 26, 240 + ((i * 41) % 120), 8);
    }
    mainTex.needsUpdate = true;
  }

  function paintSide(time: number) {
    const ctx = sideCanvas.getContext('2d')!;
    const { width: W, height: H } = sideCanvas;
    ctx.fillStyle = '#12171c';
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = 'rgba(160,172,184,0.12)';
    ctx.lineWidth = 1;
    for (let x = 60; x < W; x += 60) { ctx.beginPath(); ctx.moveTo(x, 40); ctx.lineTo(x, H - 30); ctx.stroke(); }
    for (let y = 40; y < H; y += 60) { ctx.beginPath(); ctx.moveTo(30, y); ctx.lineTo(W - 30, y); ctx.stroke(); }
    const traces: [string, number, number][] = [['#8fb3c9', 1.0, 0], ['#c3a86b', 0.6, 1.7], ['#ff7a1a', 0.35, 3.1]];
    for (const [color, amp, phase] of traces) {
      ctx.strokeStyle = color;
      ctx.lineWidth = 3;
      ctx.beginPath();
      for (let i = 0; i <= 120; i++) {
        const x = 30 + (i / 120) * (W - 60);
        const y = H / 2 - Math.sin(i * 0.11 + phase + time * 0.6) * 150 * amp - Math.sin(i * 0.037 + phase) * 40;
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      }
      ctx.stroke();
    }
    sideTex.needsUpdate = true;
  }

  let sideClock = -1;

  return {
    mainTex,
    sideTex,
    update(state: ScreenState) {
      if (state.focusTitle !== lastFocus) {
        lastFocus = state.focusTitle;
        paintMain(state);
      }
      // The telemetry plot drifts slowly; repaint a few times a second, not every frame.
      if (state.time - sideClock > 0.25) {
        sideClock = state.time;
        paintSide(state.time);
      }
    },
  };
}
