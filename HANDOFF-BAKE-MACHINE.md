# Handoff: the bake machine

This file is the whole job for the machine that runs the lighting bake. **That machine bakes and
nothing else.** Another machine owns the code.

---

## Scope — read this before doing anything

**You may:**
1. Clone/pull this repo and check out the branch named below.
2. Run the bake commands in `BAKE.md`, exactly as written.
3. Watch the bake: check progress, catch failures, restart a state that died, re-run one at higher
   samples if the output is visibly blotchy.
4. Commit the bake outputs and push them.
5. Write one short log of what ran and what came out (`docs/bake-log-<date>.md`).

**You may not — no matter how obvious the improvement looks:**
- Change anything under `src/`, `scripts/`, `blender/scripts/`, `blender/source/`, `assets/`,
  `public/` (except `public/assets/lightmaps/`, which is the bake's own output).
- "Fix" the bake script, the models, the materials, the lighting values, the UVs, or the pipeline.
  If the script is wrong, **stop and report it** — do not repair it. The other machine will.
- Optimise, refactor, tidy, upgrade dependencies, reformat, or run the web app's test suites.
- Merge, rebase, force-push, or touch any branch other than the bake branch.
- Start a dev server, run the room in a browser, or benchmark anything.

If a bake fails twice for the same reason, stop and report. Do not improvise a workaround.

**Why the discipline:** the bake is a long unattended job whose only value is that its inputs are
exactly the ones the other machine measured and verified. Any edit here silently invalidates it.

---

## Before you start

| requirement | value |
|---|---|
| Blender | 5.0.x preferred, **5.2 LTS is fine**. The rule is that *all five states come from the same build* — mixing versions within a set is what breaks it. The version is recorded in `manifest.json`. |
| GPU | Cycles with GPU compute enabled is strongly preferred; CPU works but is hours slower |
| Disk | ~2–4 GB free for intermediate EXRs |
| Git | push access to `origin`, on the bake branch only |
| Clone | a fresh clone or a pull to the exact commit named in the work order below |

Check Blender first: `blender --version`. Anything in 5.0.x–5.2.x is fine; note the exact version in
your log. On Windows the binary is typically
`C:\Program Files\Blender Foundation\Blender 5.2\blender.exe` and is not on PATH — call it by full
path, or add it to PATH for the session. Below 5.0 or above 5.2, stop and report.

---

## Work order

```
repo:     <this repository>
branch:   bake/20260927            # created from main; pull it, do not create or merge branches
commit:   be89671
states:   day, golden, evening, night, neutral
command:  see BAKE.md
output:   public/assets/lightmaps/<state>/*.exr + *.png, public/assets/lightmaps/manifest.json
```

Run the states **in the order listed**. `neutral` is the cheapest — run it first as a smoke test and
look at the result before committing hours to the other four.

---

## What "it looks right" means

Open the written EXR/PNG and check, per group:

- **Even, not blotchy.** Splotchy patches mean too few samples or denoiser starvation — re-run that
  state with more samples (the flag is in `BAKE.md`).
- **No light bleeding across UV islands.** Bright halos leaking onto unrelated parts of the atlas
  means the margin is too small — report it; do not edit the script.
- **No fully black or fully white atlases.** Either means the bake found no lighting (or blew out);
  report it.
- **Seams:** faint seams at island borders are expected and acceptable; hard black seams are not.

Record what you saw for each state in the log. One sentence each is enough.

---

## Committing

Commit only:

```
public/assets/lightmaps/**        # the bake output
docs/bake-log-<date>.md           # your log
```

One commit per state is ideal (`bake: day at 2048 px, 512 samples, 41 min`), or one commit for all
five if you ran them in a single unattended pass. Then push the bake branch. **Do not merge it.**

Commit message format:

```
bake: <state> at <resolution>, <samples> samples, <wall clock>

Blender <version>, <GPU or CPU>, source hash <from manifest.json>.
```

Nothing else goes in the commit — no stray temp files, no `.blend1` backups, no renders.

---

## When you are done

Push, then report back with:

1. The branch and commit hashes you pushed.
2. Per state: resolution, samples, wall clock, output size, and your one-line look assessment.
3. Anything that failed, and what the error said — verbatim, not summarised.

Then stop. The other machine pulls from here, wires the lightmaps into the runtime, measures the
frame cost, and decides what ships.

---

## If something is wrong

Report, do not fix. Useful report:

> `bake_lighting.py` state `golden` failed after 6 min:
> `RuntimeError: no active UV layer 'Lightmap' on object shelf_boards`
> Blender 5.0.1, GPU, commit abc1234. Ran twice, same error both times.

Unhelpful report: "it broke, I patched the UV lookup and it works now" — that invalidates the bake.
