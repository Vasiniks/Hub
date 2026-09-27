# Follow-up: keep the owner's blade head (branch ws/models)

The owner reviewed your rebuild and chose: **model the head as the long oval blade their STL
actually has, and keep lighting it with the existing circular-disk model.** Your circular 85 mm
head is not what their lamp looks like — the cantilevered blade is the defining feature, and the
current result reads thin and insubstantial at seated distance.

## What to change
1. **Head geometry: the owner's blade.** Take the proportions from the STL (oval ≈ 26.9 × 20.6
   source units, flat, cantilevered forward over the ball joint). At room scale make it roughly
   **300 mm long × 80 mm wide × 12–16 mm thick**, keeping the STL's aspect and its forward
   cantilever and slight downward tilt. It should read as a modern LED bar, not a dish.
2. **Light model: unchanged.** Keep `lampDisk.ts` and `LAMP_DISK_RADIUS` as they are, but put the
   disk at the blade's centre and size it to the blade's **short axis** (r ≈ 0.040 m). Update the
   sidecar `socket` to the blade's emitting face and widen the beam/`LAMP_ANGLE` only as much as
   it takes to cover the same desk pool the old lamp lit — the pool must land back where it was
   (over the cube/mug/keyboard working area), not left-and-back as it does now. Verify with
   `scripts/lamp-shots.mjs` and by measuring the pool centre as you did before.
3. **Emissive/diffuser**: the blade's underside is the glowing face — make that the diffuser
   material so the bar reads as lit from the desk's point of view, and keep the bloom behaviour
   sane at night (do not blow it out; check hour 21 and 18.5).
4. **Substance**: thicken the twin bars and widen/weight the base enough that the lamp does not
   read as spindly at seated distance, while staying recognisably the owner's design.

## Constraints
Same as before: pipeline unchanged, tri budget (your rebuild was 3282 — a blade may cost a little
more, keep the lamp under ~5000), `npx tsc --noEmit` clean, all verify scripts green, MANIFEST
licence line unchanged and honest (owner-supplied STL, used with permission, NOT CC0).

## Also settle the +0.65 ms
Your ABAB runs showed the new lamp consistently ~0.6–0.7 ms slower even when it ran first and
cooler, and you attributed it to thermal drift. Settle it: the suspect is the **pool position** —
the lamp's PCSS runs for lit pixels in the cone, so moving the pool changes how much of the screen
pays for it. Re-measure after the pool is back in its old place, with 4+ interleaved rounds, and
report the number honestly either way.

## Done means
Night close-ups and frozen-grain before/after at hours 13/18.5/21, pool centre measured, tri count
and GLB size, interleaved A/B frame times, verifies green, report appended.
