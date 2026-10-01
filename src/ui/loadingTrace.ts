/**
 * The monitor is already on.
 *
 * While the room loads, the loader shows the same Lorenz system that runs on the desk monitor
 * once inside, and the visitor can drop points into it: a click (or Enter / Space on the focused
 * figure) starts a new trajectory where they pointed, and they watch it get pulled onto the same
 * two wings as every other start. That is the one thing a strange attractor says, and it takes
 * about a second to see — the length of the wait. Simulation and drawing: `lorenzToy.ts`.
 *
 * Budget (the loader may only use what the GPU and network are not using):
 * - Canvas2D, one 384×192 canvas (× devicePixelRatio, capped at 2), repainted at 24 Hz.
 *   No WebGL: the room is compiling shaders and uploading textures in this window.
 * - Drawn in a worker on an OffscreenCanvas, so it keeps moving while the page's main thread is
 *   blocked by the room's own loading work. Without OffscreenCanvas it runs on the page, and
 *   only then is the simulation fetched into the page (a dynamic import, not in the bundle).
 * - Invisible until it is running: the visitor never sees a figure that does not answer.
 * - `stop()` is synchronous: worker terminated (or loop cancelled), listeners removed, focus
 *   released. `loading.ts` calls it before the reveal, so it never holds the reveal hostage.
 *
 * Honesty: this module never reports progress; the bar stays purely stage-driven.
 *
 * Accessibility: the canvas sits in a real <button> with its own label, so it is reachable by
 * Tab and works with Enter/Space; ←/→ turn the figure (the pointer does the same by hovering).
 * Under `prefers-reduced-motion` nothing loops: the figure is painted once, and a dropped point
 * is integrated to its end at once and drawn as a finished path.
 */
import { TOY_H, TOY_HZ, TOY_TURN, TOY_W } from './lorenzToySize';

export interface LoadingTrace {
  /** Stop for good: nothing runs, nothing listens, focus is back on the page. Idempotent. */
  stop(): void;
}

/** What the page-side controls drive, wherever the figure is actually drawn. */
interface Driver {
  drop(at: [number, number] | null): void;
  turnTo(target: number): void;
  stop(): void;
}

const NOOP: LoadingTrace = { stop() {} };
let instance: LoadingTrace | null = null;

/** The one trace for this page; a second call returns the same one. */
export function loadingTrace(): LoadingTrace {
  if (instance) return instance;
  const canvas = document.getElementById('loader-trace') as HTMLCanvasElement | null;
  const button = document.getElementById('loader-toy') as HTMLButtonElement | null;
  instance = canvas && button ? create(canvas, button) : NOOP;
  return instance;
}

function create(canvas: HTMLCanvasElement, button: HTMLButtonElement): LoadingTrace {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.round(TOY_W * dpr);
  canvas.height = Math.round(TOY_H * dpr);
  // Shown only once a figure is on it and it answers input.
  const live = () => (button.dataset.live = '');

  const driver = startInWorker(canvas, dpr, reduced, live) ?? startOnPage(canvas, dpr, reduced, live);

  let turnTarget = 0;
  function onClick(e: MouseEvent) {
    const r = canvas.getBoundingClientRect();
    // Keyboard activation (detail 0) or a click on the border: drop one in from above.
    const pointed = e.detail > 0 && r.width > 0 && e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
    driver.drop(pointed ? [((e.clientX - r.left) / r.width) * TOY_W, ((e.clientY - r.top) / r.height) * TOY_H] : null);
    // After the first drop the caption turns from the instruction to what they just saw.
    button.dataset.dropped = '';
  }
  function onKey(e: KeyboardEvent) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    turnTarget = Math.max(-TOY_TURN, Math.min(TOY_TURN, turnTarget + (e.key === 'ArrowLeft' ? -0.15 : 0.15)));
    driver.turnTo(turnTarget);
  }
  function onMove(e: PointerEvent) {
    const r = canvas.getBoundingClientRect();
    if (r.width <= 0) return;
    turnTarget = ((e.clientX - r.left) / r.width - 0.5) * 1.4 * TOY_TURN;
    driver.turnTo(turnTarget);
  }
  button.addEventListener('click', onClick);
  button.addEventListener('keydown', onKey);
  if (!reduced) button.addEventListener('pointermove', onMove);

  let stopped = false;
  return {
    stop() {
      if (stopped) return;
      stopped = true;
      driver.stop();
      button.removeEventListener('click', onClick);
      button.removeEventListener('keydown', onKey);
      button.removeEventListener('pointermove', onMove);
      // Hand the keyboard back to the room: Space on <body> means "sit" once inside.
      if (document.activeElement === button) button.blur();
      button.disabled = true;
    },
  };
}

function startInWorker(canvas: HTMLCanvasElement, dpr: number, reduced: boolean, live: () => void): Driver | null {
  if (!('transferControlToOffscreen' in canvas) || typeof Worker === 'undefined') return null;
  let worker: Worker;
  try {
    worker = new Worker(new URL('./loadingTrace.worker.ts', import.meta.url), { type: 'module' });
  } catch {
    return null;
  }
  const offscreen = canvas.transferControlToOffscreen();
  // If the worker never starts, the figure simply stays hidden; loading is unaffected.
  worker.onmessage = (e: MessageEvent<{ type: string }>) => {
    if (e.data.type === 'live') live();
  };
  worker.postMessage({ type: 'init', canvas: offscreen, dpr, reduced }, [offscreen]);
  return {
    drop: (at) => worker.postMessage({ type: 'drop', at }),
    turnTo: (target) => worker.postMessage({ type: 'turn', target }),
    // Synchronous from the page's side: no further frame is drawn after this returns.
    stop: () => worker.terminate(),
  };
}

/** Fallback without OffscreenCanvas: the same figure on the page's own thread. */
function startOnPage(canvas: HTMLCanvasElement, dpr: number, reduced: boolean, live: () => void): Driver {
  let toy: import('./lorenzToy').LorenzToy | null = null;
  let stopped = false;
  let raf = 0;
  let timer = 0;
  const frame = (now: number, last: number) => {
    if (stopped || !toy) return;
    toy.tick((now - last) / 1000);
    timer = window.setTimeout(() => {
      if (!stopped) raf = requestAnimationFrame((t) => frame(t, now));
    }, 1000 / TOY_HZ);
  };
  const ctx = canvas.getContext('2d', { alpha: false });
  if (ctx) {
    import('./lorenzToy')
      .then(({ createLorenzToy }) => {
        if (stopped) return;
        toy = createLorenzToy(ctx, dpr, reduced);
        toy.paint();
        live();
        const start = performance.now();
        if (!reduced) raf = requestAnimationFrame((t) => frame(t, start));
      })
      .catch(() => {}); // the figure stays hidden; loading is unaffected
  }
  return {
    drop: (at) => toy?.drop(at),
    turnTo: (target) => toy?.turnTo(target),
    stop: () => {
      stopped = true;
      cancelAnimationFrame(raf);
      clearTimeout(timer);
    },
  };
}
