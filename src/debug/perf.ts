/** Debug-only frame profiler: CPU time per stage, frame-time distribution, draw calls per whole frame. */
const CAP = 6000;

function push(list: number[], v: number) {
  if (list.length < CAP) list.push(v);
}

function stats(list: number[]) {
  if (!list.length) return null;
  const sorted = [...list].sort((a, b) => a - b);
  const q = (p: number) => sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))];
  const avg = list.reduce((a, b) => a + b, 0) / list.length;
  return { avg: +avg.toFixed(2), p50: +q(0.5).toFixed(2), p95: +q(0.95).toFixed(2), max: +sorted[sorted.length - 1].toFixed(2) };
}

export class FramePerf {
  readonly enabled: boolean;
  private mark = 0;
  private frameStart = 0;
  private lastFrame = 0;
  private startedAt = 0;
  private frames = 0;
  private deltas: number[] = [];
  private cpu: number[] = [];
  private calls: number[] = [];
  private tris: number[] = [];
  private stages = new Map<string, number[]>();
  private current: Record<string, number> = {};
  private slow: { at: number; cpu: number; programs: number; stages: Record<string, number> }[] = [];

  constructor(enabled: boolean) {
    this.enabled = enabled;
  }

  beginFrame(now: number) {
    if (!this.enabled) return;
    if (this.lastFrame) push(this.deltas, now - this.lastFrame);
    if (!this.startedAt) this.startedAt = now;
    this.lastFrame = now;
    this.frames++;
    this.frameStart = this.mark = performance.now();
    this.current = {};
  }

  lap(name: string) {
    if (!this.enabled) return;
    const t = performance.now();
    let list = this.stages.get(name);
    if (!list) this.stages.set(name, (list = []));
    push(list, t - this.mark);
    this.current[name] = +(t - this.mark).toFixed(1);
    this.mark = t;
  }

  endFrame(calls: number, triangles: number, programs = 0) {
    if (!this.enabled) return;
    const cpu = performance.now() - this.frameStart;
    push(this.cpu, cpu);
    push(this.calls, calls);
    push(this.tris, triangles);
    // Keep the anatomy of slow frames: when, which stage, and how many shader programs existed.
    if (cpu > 35 && this.slow.length < 60) {
      this.slow.push({ at: Math.round(performance.now() - this.startedAt), cpu: +cpu.toFixed(1), programs, stages: this.current });
    }
  }

  reset() {
    this.deltas = [];
    this.cpu = [];
    this.calls = [];
    this.tris = [];
    this.stages.clear();
    this.slow = [];
    this.startedAt = 0;
    this.lastFrame = 0;
    this.frames = 0;
  }

  snapshot(pixelRatio: number) {
    const elapsed = performance.now() - this.startedAt;
    const memory = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory;
    return {
      frames: this.frames,
      fps: +(this.frames / (elapsed / 1000)).toFixed(1),
      frameMs: stats(this.deltas),
      /** Frames that took more than 1.5 display intervals at 60 Hz: visible hitches under vsync. */
      missed: this.deltas.filter((d) => d > 25).length,
      cpuMs: stats(this.cpu),
      stages: Object.fromEntries([...this.stages].map(([k, v]) => [k, stats(v)])),
      drawCalls: stats(this.calls),
      triangles: this.tris.length ? Math.round(this.tris.reduce((a, b) => a + b, 0) / this.tris.length) : 0,
      heapMB: memory ? +(memory.usedJSHeapSize / 1048576).toFixed(1) : null,
      pixelRatio,
      slow: this.slow,
    };
  }
}
