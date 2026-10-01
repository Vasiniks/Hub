# Workstream: give the visitor something to do while the room loads

Read `.claude/briefs/_common.md` first. Branch `ws/loading`, worktree `~/Documents/GitHub/hub-wt-loading`.

**The problem, measured.** On the live site the room takes **5.7 s** from navigation to interactive
(`https://vasiniks.github.io/Hub/`, cold). Locally it is ~1.7 s. For those seconds the visitor gets
a progress bar and nothing else, and the first thing a portfolio says about its author is what it
does with a visitor's attention while it makes them wait.

**Your job.** Make that wait worth something. Not a spinner with better manners — something the
visitor can actually do or watch, that belongs to this room and this person.

## Rules that decide whether it ships

1. **It must not make the wait longer.** The loader's whole budget is what the GPU and network are
   not using. Measure with `node scripts/startup-trace.mjs` before and after: "loader hidden" must
   not regress by more than 5%. If your idea costs more than that, make it cheaper or drop it.
2. **It must not steal the GPU.** The room is compiling shaders and uploading textures during this
   window (`view.warmUp`). Canvas2D, CSS or DOM is fine; a second WebGL context is not.
3. **It must end cleanly.** When the room is ready the visitor goes to the room — the activity never
   holds the reveal hostage, and anything they started is either finished or clearly dropped. The
   reveal already exists (`#veil`, `is-lifted`); do not fight it.
4. **Accessible.** Keyboard-reachable, screen-reader sane, and it respects
   `prefers-reduced-motion` — `scripts/verify-motion.mjs` must stay green.
5. **No third-party anything.** No new dependency, no remote asset, no font. The bundle is already
   868 kB; your addition should be measured in single-digit kB.

## Direction

Decide the idea yourself and say why you chose it, but it should be *of this room*, not a generic
mini-game bolted on. The room's own material is the richest source: the Lorenz attractor that runs
on the monitor (`src/scene/lorenz.ts`), the speedcube, the desk lamp, the objects the visitor is
about to be able to open. The loader already knows the real stages (`src/ui/loading.ts` —
`loader.advance(stage)`), so the progress it reports is honest; keep it that way.

Two things to avoid because they are the default answer: a tips carousel, and a progress bar with a
percentage that lies. If you find yourself writing "Did you know…", stop.

Build one idea properly rather than three half-built ones.

## Done means

- Startup trace before and after, pasted in your report.
- A screenshot (or a few frames) of the loading state in your report, plus the reduced-motion
  variant.
- `npx tsc --noEmit -p .` clean; `verify-room`, `verify-a11y`, `verify-motion` green against your
  own port via `ROOM_URL`.
- Report at `.claude/briefs/report-loading.md`.
