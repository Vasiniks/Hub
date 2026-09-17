import * as THREE from 'three';

/**
 * Uniforms every physical material reads from one shared object: renderer-wide inputs that shader
 * patches add (see areaLights.ts, lampDisk.ts), which three has no per-scene slot for.
 *
 * Bound through a class-wide compile hook; hooks set on material instances chain to it.
 * Uniforms a program does not declare are simply not uploaded.
 */
const shared: Record<string, THREE.IUniform> = {};

export function shareUniform(name: string, uniform: THREE.IUniform) {
  shared[name] = uniform;
  THREE.MeshStandardMaterial.prototype.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, shared);
  };
}
