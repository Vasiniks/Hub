/**
 * The loading figure's shared numbers, kept apart from the simulation so the page can size the
 * canvas and clamp input without bundling `lorenzToy.ts` (which normally runs in the worker).
 */

/** Drawing units. The backing store is these times devicePixelRatio (capped at 2). */
export const TOY_W = 384;
export const TOY_H = 192;
/** Repaints per second. The figure drifts slowly; more than this is invisible. */
export const TOY_HZ = 24;
/** How far the visitor can turn the figure, either way, in radians. */
export const TOY_TURN = 0.5;
