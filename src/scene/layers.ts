/** Layer 1 holds UI-in-the-world (attention dots): seen by the camera, skipped by AO, outlines, and environment capture. */
export const OVERLAY_LAYER = 1;

/**
 * Layer 2 holds what only the environment capture sees: emitters standing in for the rect lights'
 * specular (see areaLights.ts), so glossy surfaces still reflect the window.
 */
export const REFLECTION_LAYER = 2;
