/**
 * §24: a minimal bar over an empty background while the scene is genuinely being prepared.
 *
 * The fill position is always "stages finished / stages total". Nothing is interpolated toward
 * a guess and nothing advances on a timer, so the bar never claims progress that has not
 * happened. The CSS transition only smooths the travel between two real positions.
 */
export function createLoader(stages: readonly string[]) {
  const root = document.getElementById('loader')!;
  const fill = document.getElementById('loader-fill')!;
  const label = document.getElementById('loader-label')!;
  let done = 0;
  /** When each stage finished, in ms since navigation start — read by the startup profiler. */
  const marks: { stage: string; at: number }[] = [];
  let current = stages[0];

  return {
    marks,
    /** Mark a stage complete and describe what is starting next. */
    advance(next?: string) {
      marks.push({ stage: current, at: Math.round(performance.now()) });
      current = next ?? current;
      done = Math.min(stages.length, done + 1);
      fill.style.transform = `scaleX(${done / stages.length})`;
      if (next) label.textContent = next;
    },
    fail(message: string) {
      label.textContent = message;
      root.classList.add('is-failed');
    },
    /** Resolves once the bar has faded, so the first real frame lands on an empty screen. */
    hide(): Promise<void> {
      fill.style.transform = 'scaleX(1)';
      root.classList.add('is-done');
      return new Promise((resolve) =>
        window.setTimeout(() => {
          root.hidden = true;
          resolve();
        }, 420),
      );
    },
  };
}
