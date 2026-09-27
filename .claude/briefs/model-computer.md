# Remodel: computer gear (branch ws/model-computer)

Read `.claude/briefs/_common.md` and `.claude/briefs/_remodel_convention.md` first.

Your group, in priority order:
1. **Monitor** — bezel with real depth and a proper screen inset, back shell with vents and a VESA
   boss, arm/stand with believable joints and a weighted base. The screen plane must stay exactly
   where `src/scene/desk.ts` expects it (`screen`, `screenCenter`, `screenSize`) because the
   attractor renders onto it and a rect-area light is attached to it.
2. **Keyboard** — TKL: case with a real profile, plate, keycaps with proper sculpting per row,
   legends if they survive at distance, feet, cable exit.
3. **MacBook** — lid/base with correct taper, hinge, keyboard well, trackpad, ports, rubber feet.
   The lid is a hero specular surface (it catches the window and the monitor) — get its curvature
   and edge radii right.
4. **Mouse** — shell curvature, button split, scroll wheel, cable or wireless as suits.
5. **PC tower / USB hub / dev board** — panel gaps, connectors, silkscreen where it reads.

Keep every mount point the runtime uses: screen plane, LED positions (`room.leds`), hub/board
hitboxes for hover and focus. Verify hovering and focusing each of these still works
(`verify-room` covers dev-board, frc-robot, notebooks).
Save `blender/source/computer.blend`.
