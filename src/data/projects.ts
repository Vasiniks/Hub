export type ProjectKind = 'major' | 'small' | 'experiment';

export type BuilderKey = 'frcRobot' | 'polyhedron' | 'notebooks' | 'devBoard' | 'partsCrate';

export interface ProjectSection {
  label: string;
  body: string;
}

export interface ProjectDef {
  id: string;
  title: string;
  kind: ProjectKind;
  kindLabel: string;
  /** True until real content replaces the placeholder copy. */
  placeholder: boolean;
  summary: string;
  sections: ProjectSection[];
  object: {
    builder: BuilderKey;
    position: [number, number, number];
    rotationY: number;
    scale?: number;
  };
  /** Local-space point the camera examines and the attention dot marks. */
  anchor: [number, number, number];
  /** Camera framing while examining: orbit around the anchor (radians, metres). */
  focus: {
    distance: number;
    yaw: number;
    pitch: number;
  };
}

const placeholderSections = (): ProjectSection[] => [
  { label: 'What I did', body: 'Placeholder.' },
  { label: 'Approach', body: 'Placeholder.' },
  { label: 'Result', body: 'Placeholder.' },
];

export const projects: ProjectDef[] = [
  {
    id: 'frc-robot',
    title: 'FRC robot',
    kind: 'major',
    kindLabel: 'Robotics',
    placeholder: false,
    summary:
      'A competition robot for the FIRST Robotics Competition: drivetrain, mechanisms, and the software that drives them under match pressure.',
    sections: [
      { label: 'What it is', body: 'Placeholder. The robot, the season, and the game it was built to play.' },
      { label: 'What I did', body: 'Placeholder. Role on the team, subsystems owned, code written.' },
      { label: 'Problem', body: 'Placeholder. The constraint or failure that shaped the design.' },
      { label: 'Approach', body: 'Placeholder. Control, autonomy, tooling, iteration loop.' },
      { label: 'Result', body: 'Placeholder. What happened at competition.' },
      { label: 'What changed after', body: 'Placeholder. What the next iteration did differently.' },
    ],
    object: { builder: 'frcRobot', position: [-0.98, 0, 0.2], rotationY: 0.78 },
    anchor: [0, 0.42, 0],
    focus: { distance: 1.1, yaw: 1.95, pitch: 0.62 },
  },
  {
    id: 'polyhedron',
    title: 'Untitled experiment',
    kind: 'experiment',
    kindLabel: 'Experiment',
    placeholder: true,
    summary: 'Brief placeholder description.',
    sections: placeholderSections(),
    object: { builder: 'polyhedron', position: [-0.5, 0.74, -0.56], rotationY: 0.3 },
    anchor: [0, 0.11, 0],
    focus: { distance: 0.52, yaw: 0.35, pitch: 0.38 },
  },
  {
    id: 'notebooks',
    title: 'Placeholder project',
    kind: 'small',
    kindLabel: 'Small project',
    placeholder: true,
    summary: 'Brief placeholder description.',
    sections: placeholderSections(),
    object: { builder: 'notebooks', position: [0.6, 0.74, -0.5], rotationY: -0.35 },
    anchor: [0, 0.05, 0],
    focus: { distance: 0.55, yaw: -0.15, pitch: 0.72 },
  },
  {
    id: 'dev-board',
    title: 'Placeholder project',
    kind: 'major',
    kindLabel: 'Software',
    placeholder: true,
    summary: 'Brief placeholder description.',
    sections: placeholderSections(),
    object: { builder: 'devBoard', position: [0.34, 0.74, -0.86], rotationY: -0.2 },
    anchor: [0, 0.03, 0],
    focus: { distance: 0.32, yaw: -0.25, pitch: 0.62 },
  },
  {
    id: 'parts-crate',
    title: 'Placeholder archive',
    kind: 'small',
    kindLabel: 'Small projects',
    placeholder: true,
    summary: 'Brief placeholder description.',
    sections: placeholderSections(),
    object: { builder: 'partsCrate', position: [0.9, 0, -0.18], rotationY: -0.45 },
    anchor: [0, 0.26, 0],
    focus: { distance: 1.0, yaw: -1.2, pitch: 0.75 },
  },
];
