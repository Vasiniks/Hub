# Report: v2-rig (branch `ws/v2-rig`, last commit 718e2e1)

The subagent returned this report as its final message (subagents cannot write report files); the
coordinator committed it. Screenshots: `.claude/briefs/report-v2-rig/`.

Measured on Windows (RTX 5070, headless Chrome 153 on D3D11), not on the target M2 Pro.

## What works (verified in a real browser)

`scripts/verify-v2.mjs` (new) drives `/?v2&debug` as a visitor would; 0 failures, 0 console errors on the dev server
and on the production bundle (`vite build` + `vite preview`):

- **Standing:** mouse look reaches its limit (yaw +0.32).
- **Sit:** scroll starts it; `sitting` at 1.3 s, `seated` by 3.9 s.
- **Seated look:** left +1.074, right −0.996, up +0.415, down −0.542 rad, with the same spring as the old room.
- **Hover:** the bookshelf shows its label and outline.
- **Click:** the camera goes to `focused` and the panel opens.
- **Back:** Esc and click-outside both return to `seated`.
- **Keyboard:** Tab, Enter and Esc drive the object nav.
- **Click while standing:** the visitor sits first, then the object opens.

The interactive object was the real baked bookrack, not a proxy. tsc clean.

**Startup** (startup-trace, dev server): v2 1.12–1.35 s.

**Frame cost** (debug bench, 1728×1000 at 1.5): v2 is 35 draw calls and 55 k triangles, ≈0.5–0.8 ms. Hover adds the
outline's half-res depth pass: calls go 35 → 71, costing ≈0.15–0.2 ms. rAF is capped at 200 fps on this machine, so
120 fps on the Mac is not verified.

## Changes

- **Rig** (`src/camera/rig.ts`): takes a `RigTuning` and a `SitChair | null`. Added a `focusFov` getter. Pitch limits
  are [down, up].
- **v2 tuning** (`src/scene/v2Layout.ts`):
  - CAM_seat / CAM_stand read from `room_public.blend`; the 54° fov matches.
  - Seated look-down limit is 0.55, not 0.72; the extra range only showed the floor under the desk.
  - `V2_ROOM` holds the measured inner wall faces.
  - v2 has no live chair, so sitting moves the camera only.
- **Prop registry** (`src/interaction/props.ts`): reuses the old modules instead of forking them.
  - `createInteraction` gained `.add()`.
  - `createPanel` gained `fillContent()`.
  - `createObjectNav` returns `{ add }`.
  - `src/scene/v2Props.ts` loads the manifest and GLBs; `src/data/v2Props.ts` is the table of interactive objects.
- **Shared fixes:**
  - The outline is a softer warm rim (`#f3e9da`, strength 1.0, divided by exposure).
  - With no AO depth, the outline renders its own depth pass, so occluded edges no longer draw through.
  - The hover label sits level with the attention dot and flips left near the screen edge.
  - Bloom is disabled by `instanceof`, not `constructor.name` (minification renamed classes, so production v2 ran
    with bloom on).
  - `verify-env.mjs` swaps ANGLE Metal for D3D11 on Windows, because Metal fell back to SwiftShader there.

## Prop-registry API

```ts
createPropRegistry(opts: { scene; camera; rig: CameraRig; outline: OutlinePass; canvas;
  seat: [x,y,z]; reducedMotion: boolean; hint: { hide(): void }; onOpen?: (id) => void }): PropRegistry
registry.register(spec: PropSpec): InteractTarget
interface PropSpec {
  id: string; label: string;
  node: THREE.Object3D | THREE.Object3D[];
  panel: PanelContent;
  focus?: { center?; distance?; yaw?; pitch?; offset? };
  dot?: [x,y,z]; lift?: boolean; tick?: (time, activity) => void;
}
```

- **Focus defaults:** the centre of the object's bounds, approached from the seat, pitch 0.32, offset 0.3. Distance
  is the bounding radius fitted to the 45° focus lens × 1.4, minimum 0.3 m.
- **Other members:** `open`, `close`, `holdLook` (call before `rig.update`), `update` (after it), `groups()` (for
  `warmUp`), `resumePending()` (from `rig.onSeated`).

## Left at the time (since resolved in integration)

- Props had no exported GLBs yet.
- Props would render black without live light.
- The panel copy is placeholder (as in the old room).
