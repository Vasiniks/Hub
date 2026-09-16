/**
 * Debug-only GPU time per render stage, from WebGL2 timer queries (`?gpu`).
 *
 * CPU profiling can't see GPU cost: the main thread just blocks inside whichever GL call hits a
 * full command buffer, so the time lands on `uniformMatrix4fv` rather than on the pass that
 * caused it. Timer queries measure the pass itself.
 *
 * Queries cannot nest, so a stage that starts inside another (shadow maps render inside the
 * scene pass) closes the outer query, runs its own, and reopens the outer one afterwards — each
 * stage reports only its own time.
 */
interface Pending {
  label: string;
  query: WebGLQuery;
}

const CAP = 4000;

export function createGpuTimer(gl: WebGL2RenderingContext, enabled: boolean) {
  const ext = enabled ? gl.getExtension('EXT_disjoint_timer_query_webgl2') : null;
  const stack: string[] = [];
  let open: Pending | null = null;
  const pending: Pending[] = [];
  const samples = new Map<string, number[]>();
  /** Per-frame totals, so a stage that runs several times a frame reports its frame cost. */
  let frameSums = new Map<string, number>();
  const frameSeries = new Map<string, number[]>();
  const framePending: { label: string; query: WebGLQuery; frame: number }[] = [];
  let frame = 0;

  function startQuery(label: string) {
    const query = gl.createQuery()!;
    gl.beginQuery(ext!.TIME_ELAPSED_EXT, query);
    open = { label, query };
  }

  function closeQuery() {
    if (!open) return;
    gl.endQuery(ext!.TIME_ELAPSED_EXT);
    pending.push(open);
    framePending.push({ ...open, frame });
    open = null;
  }

  function push(label: string, ms: number) {
    let list = samples.get(label);
    if (!list) samples.set(label, (list = []));
    if (list.length < CAP) list.push(ms);
  }

  return {
    enabled: !!ext,
    begin(label: string) {
      if (!ext) return;
      closeQuery();
      stack.push(label);
      startQuery(label);
    },
    end() {
      if (!ext) return;
      closeQuery();
      stack.pop();
      if (stack.length) startQuery(stack[stack.length - 1]);
    },
    /** Wrap a method so every call is timed under `label`. */
    wrap<T extends object>(target: T, method: keyof T, label: string) {
      if (!ext) return;
      const original = (target[method] as unknown as (...a: unknown[]) => unknown).bind(target);
      const self = this;
      (target as Record<keyof T, unknown>)[method] = (...args: unknown[]) => {
        self.begin(label);
        try {
          return original(...args);
        } finally {
          self.end();
        }
      };
    },
    /** Call once per frame: collects finished queries and closes the frame's totals. */
    endFrame() {
      if (!ext) return;
      frame++;
      const disjoint = gl.getParameter(ext.GPU_DISJOINT_EXT);
      for (let i = framePending.length - 1; i >= 0; i--) {
        const p = framePending[i];
        if (!gl.getQueryParameter(p.query, gl.QUERY_RESULT_AVAILABLE)) continue;
        if (!disjoint) {
          const ms = gl.getQueryParameter(p.query, gl.QUERY_RESULT) / 1e6;
          push(p.label, ms);
          frameSums.set(`${p.frame}|${p.label}`, (frameSums.get(`${p.frame}|${p.label}`) ?? 0) + ms);
        }
        gl.deleteQuery(p.query);
        framePending.splice(i, 1);
      }
      pending.length = 0;
      // Fold completed frames' per-label totals into a per-frame series.
      if (frameSums.size > 2000) {
        for (const [k, v] of frameSums) {
          const label = k.slice(k.indexOf('|') + 1);
          let list = frameSeries.get(label);
          if (!list) frameSeries.set(label, (list = []));
          if (list.length < CAP) list.push(v);
        }
        frameSums = new Map();
      }
    },
    reset() {
      samples.clear();
      frameSeries.clear();
      frameSums = new Map();
    },
    snapshot() {
      for (const [k, v] of frameSums) {
        const label = k.slice(k.indexOf('|') + 1);
        let list = frameSeries.get(label);
        if (!list) frameSeries.set(label, (list = []));
        if (list.length < CAP) list.push(v);
      }
      frameSums = new Map();
      const out: Record<string, { perFrameAvg: number; perFrameP95: number; calls: number }> = {};
      let total = 0;
      for (const [label, list] of frameSeries) {
        const sorted = [...list].sort((a, b) => a - b);
        const avg = list.reduce((a, b) => a + b, 0) / list.length;
        total += avg;
        out[label] = {
          perFrameAvg: +avg.toFixed(2),
          perFrameP95: +sorted[Math.floor(sorted.length * 0.95)].toFixed(2),
          calls: samples.get(label)?.length ?? 0,
        };
      }
      return { stages: out, totalAvg: +total.toFixed(2) };
    },
  };
}

export type GpuTimer = ReturnType<typeof createGpuTimer>;
