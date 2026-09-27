# Fix the bake script (branch ws/bake) — reported from the bake machine

The operator ran `neutral` at 256 spp / 1024 px on Windows (Blender 5.2.2 LTS, RTX 5070) and it
failed twice, identically, on the first group. They correctly did not patch it. Fix these, verify,
and push. Do not redesign the bake.

## 1. The bake result is never written to disk (the actual crash)
```
Info: Baking map saved to internal image, save it externally or pack it.
Traceback (most recent call last):
  File "blender/scripts/bake_lighting.py", line 657, in bake_state
    "files": {os.path.basename(exr_path): os.path.getsize(exr_path),
FileNotFoundError: [WinError 2] ... 'public/assets/lightmaps\\neutral\\trim.exr'
```
The bake lands in an internal image and nothing saves it before `getsize` is called. Save the image
explicitly after the bake (EXR master via `save_render` with the float settings you intend, PNG
preview separately), create the output directory first, and only then stat the files. Confirm the
pixels are real: a saved-but-empty image is the other failure mode — assert non-zero size and, for
the smoke test, that the image is not uniformly black.

## 2. Windows paths
The traceback shows `public/assets/lightmaps\neutral\trim.exr` — mixed separators. Build every path
with `os.path.join` / `pathlib.Path` (no hardcoded `/`), and pass absolute paths to Blender's image
save. Blender on Windows also chokes on `//`-relative paths unless you mean blend-relative.

## 3. Exit code lies
Blender exited **0** after the Python exception, so a batch loop reports every state as success.
Wrap `main()` so any exception prints the traceback and calls `sys.exit(1)`.

## 4. Cycles device
The script never sets a device, so it ran on CPU on a machine with an RTX 5070; the operator had to
inject a wrapper. Add `--device auto|gpu|cpu` (default `auto`): enable the best available backend
(OptiX, then CUDA, then HIP/Metal), set `scene.cycles.device`, activate the devices in preferences,
print which device and backend is in use, and fall back to CPU with a printed warning. This must
survive `--factory-startup`.

## 5. Settle the EXR question (docs contradict)
`BAKE.md` says do not commit the ~1.1 GB EXR masters; `HANDOFF-BAKE-MACHINE.md` lists `*.exr` in the
output line. Decide: **PNG previews + `manifest.json` are committed; EXR masters stay local** and
are listed in `.gitignore` under `public/assets/lightmaps/**/*.exr`. Make both documents say that,
and make the manifest record the EXR filenames and sizes even though they are not committed. If you
think the EXRs must ship, say why with numbers instead.

## Verify before you push
Run a real smoke test here: `neutral` on two groups at low samples, then confirm on disk that each
PNG and EXR exists, is non-zero, and is not uniformly black (check with Python/PIL). Then run one
state at moderate settings on a couple of groups to prove the save path holds at size. Show the file
listing and the pixel check in your report. Also state the wall clock you measured so the operator
has an estimate.

Commit on `ws/bake`. Do not touch `src/`. Append to `.claude/briefs/report-bake.md`.
