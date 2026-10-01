/**
 * The loading figure, off the main thread.
 *
 * While the room loads, the page's main thread is often blocked for seconds at a time —
 * synchronous shader compiles in `view.warmUp`, GLB parsing. A figure drawn there freezes for
 * exactly those seconds (measured: up to 4.5 s still on a 9.4 s Windows/D3D11 load). Drawn here
 * on an OffscreenCanvas, it keeps moving through them. Clicks still arrive via the page, so a
 * drop made during a stall lands when the stall ends.
 */
import { createLorenzToy, type LorenzToy } from './lorenzToy';
import { TOY_HZ } from './lorenzToySize';

type Msg =
  | { type: 'init'; canvas: OffscreenCanvas; dpr: number; reduced: boolean }
  | { type: 'drop'; at: [number, number] | null }
  | { type: 'turn'; target: number };

const scope = self as unknown as {
  onmessage: ((e: MessageEvent<Msg>) => void) | null;
  postMessage(m: unknown): void;
};

let toy: LorenzToy | null = null;

scope.onmessage = (e) => {
  const m = e.data;
  if (m.type === 'init') {
    const ctx = m.canvas.getContext('2d', { alpha: false, willReadFrequently: true });
    if (!ctx) return;
    toy = createLorenzToy(ctx, m.dpr, m.reduced);
    toy.paint();
    scope.postMessage({ type: 'live' });
    if (m.reduced) return;
    // Timer-paced, not rAF: the figure needs no more than TOY_HZ and must not wait on the page.
    let last = performance.now();
    setInterval(() => {
      const now = performance.now();
      toy!.tick((now - last) / 1000);
      last = now;
    }, 1000 / TOY_HZ);
  } else if (m.type === 'drop') toy?.drop(m.at);
  else if (m.type === 'turn') toy?.turnTo(m.target);
};
