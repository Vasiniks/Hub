import type { PropFocus, PanelContent } from '../interaction/props';
import { projects } from './projects';

/**
 * Which nodes in the v2 room are interactive, and what they open.
 *
 * Each entry names where its node(s) come from and is registered by `startV2` through
 * `createPropRegistry().register()` once that node exists. An entry whose source has not loaded
 * (a props GLB that has not been exported yet) is skipped silently, so props can be listed here
 * before their files land.
 *
 * - `baked`: name prefixes in the baked room atlases (fixtures baked into the lightmap).
 * - `props`: name prefixes across the props GLBs (`public/assets/v2/props/`).
 * - `file`: a whole props GLB by manifest name (`robot`) or file (`robot.glb`).
 */
export interface V2PropDef {
  id: string;
  label: string;
  source: { baked: string[] } | { props: string[] } | { file: string };
  panel: PanelContent;
  focus?: PropFocus;
  dot?: [number, number, number];
  lift?: boolean;
  /** Per-frame animation (the robot's status lens, a screen); `activity` 0→1 under attention. */
  tick?: (time: number, activity: number) => void;
}

/**
 * A panel from the project copy in `projects.ts`, so the default room's text and the v2 room's
 * stay one source. `title` overrides the project title where the v2 object is a different thing
 * (the brass Lorenz sculpture took the polyhedron's place).
 */
function projectPanel(id: string, title?: string): PanelContent {
  const p = projects.find((q) => q.id === id);
  if (!p) throw new Error(`v2Props: no project '${id}'`);
  return { kind: p.kindLabel, title: title ?? p.title, summary: p.summary, sections: p.sections };
}

export const v2Props: V2PropDef[] = [
  {
    id: 'frc-robot',
    label: 'FRC robot',
    source: { file: 'robot' },
    panel: projectPanel('frc-robot'),
    // From the room's open side, looking down onto the mechanisms, as in the default room.
    focus: { yaw: 2.05, pitch: 0.6 },
    lift: false,
  },
  {
    id: 'lorenz',
    label: 'Lorenz attractor',
    source: { props: ['lorenz_sculpture'] },
    panel: projectPanel('polyhedron', 'Lorenz attractor'),
  },
  {
    // The STM corner: stage, copper Faraday box, preamp, meter and the Teensy breadboard.
    id: 'lab-bench',
    label: 'Lab bench',
    source: { props: ['elec_stm_stage_grp', 'elec_faraday_grp', 'elec_preamp_grp', 'elec_multimeter_grp', 'elec_breadboard_grp'] },
    panel: projectPanel('dev-board'),
    lift: false,
  },
  {
    id: 'notebooks',
    label: 'Notes',
    source: { props: ['elec_notes', 'paper'] },
    panel: projectPanel('notebooks'),
  },
  {
    // The wall shelf, baked into the furniture atlas. Its books and items are not in the bake (they
    // come with the props export), so for now this is the empty board with its brackets and ends.
    id: 'bookshelf',
    label: 'Bookshelf',
    source: { baked: ['bookrack_'] },
    // TEMPORARY copy, like every panel in the default room: content comes later.
    panel: {
      kind: 'From the shelf',
      title: 'Bookshelf',
      summary: 'Placeholder. What is on the shelf, and why it has stayed there.',
      sections: [
        { label: 'Reading', body: 'Placeholder. The books, once they are on the shelf.' },
        { label: 'Notes', body: 'Placeholder. What each one changed, and what it is still good for.' },
      ],
    },
    // Square on to the wall it hangs on (from +x), a little above. Far enough back that the whole
    // 0.77 m board sits in the left half of the frame, clear of the panel.
    focus: { yaw: Math.PI / 2, pitch: 0.1, distance: 1.25, offset: 0.2 },
    // A wall fixture with its shadow baked around it: it must not bob when looked at.
    lift: false,
  },
];
