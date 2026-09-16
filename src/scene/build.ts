import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

/** Small geometry helpers shared by every builder in the room. */

export function shadowed<T extends THREE.Object3D>(o: T, cast = true, receive = true): T {
  o.traverse((c) => {
    if ((c as THREE.Mesh).isMesh) {
      c.castShadow = cast;
      c.receiveShadow = receive;
    }
  });
  return o;
}

/**
 * A box with real bevels. Every hard edge in the room goes through here: a 3–8 mm radius is
 * what catches a highlight and separates one white object from another white object.
 */
export function rboxGeo(w: number, h: number, d: number, r = 0.006, segments = 2) {
  const radius = Math.min(r, w / 2 - 1e-4, h / 2 - 1e-4, d / 2 - 1e-4);
  return new RoundedBoxGeometry(w, h, d, segments, radius);
}

export function rbox(w: number, h: number, d: number, mat: THREE.Material, r = 0.006) {
  return shadowed(new THREE.Mesh(rboxGeo(w, h, d, r), mat));
}

export function at<T extends THREE.Object3D>(o: T, x: number, y: number, z: number, parent?: THREE.Object3D): T {
  o.position.set(x, y, z);
  parent?.add(o);
  return o;
}

/** A cylinder spanning two points: arm segments, cables, rods. */
export function rod(from: THREE.Vector3, to: THREE.Vector3, radius: number, mat: THREE.Material, segments = 10) {
  const len = from.distanceTo(to);
  const mesh = shadowed(new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, len, segments), mat));
  mesh.position.copy(from).lerp(to, 0.5);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), to.clone().sub(from).normalize());
  return mesh;
}

/** Deterministic pseudo-random: placement jitter has to be the same on every load. */
export function rand(seed: number) {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
}
