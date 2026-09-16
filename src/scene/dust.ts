import * as THREE from 'three';
import { DUST } from './layout';

/**
 * §7: a few motes of dust drifting through the lamp beam.
 *
 * Not volumetric smoke and not a particle system in the usual sense — one additive point
 * cloud whose entire motion lives in the vertex shader, so the CPU cost per frame is four
 * uniform writes. A mote only lights up when it is genuinely inside the lamp's cone and
 * close enough to it, which is why the effect reads as dust in a beam rather than as a haze
 * hanging in the room.
 *
 * The whole thing switches off when the lamp is dark, so it costs nothing in daylight.
 */
export function createDust(scene: THREE.Scene) {
  const count = DUST.count;
  const positions = new Float32Array(count * 3);
  const seeds = new Float32Array(count * 3);
  let s = 1337;
  const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < count; i++) {
    positions[i * 3] = (rnd() - 0.5) * 2 * DUST.spread[0];
    positions[i * 3 + 1] = (rnd() - 0.5) * 2 * DUST.spread[1];
    positions[i * 3 + 2] = (rnd() - 0.5) * 2 * DUST.spread[2];
    seeds[i * 3] = rnd() * 6.283;
    seeds[i * 3 + 1] = 0.4 + rnd() * 1.4;
    seeds[i * 3 + 2] = 0.35 + rnd() * 0.65;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('seed', new THREE.BufferAttribute(seeds, 3));
  // The shader places every mote in world space, so the object matrix stays at the origin and
  // only the bounding sphere is moved — otherwise the centre offset would be applied twice.
  geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), Math.hypot(...DUST.spread) + 0.2);

  const uniforms = {
    uTime: { value: 0 },
    uCenter: { value: new THREE.Vector3() },
    uOrigin: { value: new THREE.Vector3() },
    uDir: { value: new THREE.Vector3(0, -1, 0) },
    uCos: { value: Math.cos(0.75) },
    uIntensity: { value: 0 },
    uSize: { value: DUST.size },
    uDrift: { value: DUST.drift },
    uColor: { value: new THREE.Color('#ffd9ab') },
  };

  const material = new THREE.ShaderMaterial({
    uniforms,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    vertexShader: /* glsl */ `
      attribute vec3 seed;
      uniform float uTime, uCos, uIntensity, uSize, uDrift;
      uniform vec3 uCenter, uOrigin, uDir;
      varying float vBright;
      void main() {
        // Slow, uncorrelated drift: dust does not fall, it wanders.
        vec3 wander = vec3(
          sin(uTime * 0.13 * seed.y + seed.x),
          sin(uTime * 0.09 * seed.y + seed.x * 1.7) * 0.7,
          cos(uTime * 0.11 * seed.y + seed.x * 2.3)
        ) * uDrift * seed.z * 12.0;
        vec3 world = uCenter + position + wander;

        vec3 toMote = world - uOrigin;
        float dist = length(toMote);
        float align = dot(toMote / max(dist, 1e-4), uDir);
        // Only inside the cone, and only near the lamp.
        float cone = smoothstep(uCos, uCos + 0.16, align);
        float falloff = 1.0 - smoothstep(0.25, 1.35, dist);
        // Uneven twinkle as motes turn in the light.
        float twinkle = 0.45 + 0.55 * pow(abs(sin(uTime * 0.7 * seed.z + seed.x * 3.1)), 3.0);
        vBright = cone * falloff * twinkle * uIntensity;

        vec4 mv = modelViewMatrix * vec4(world, 1.0);
        gl_Position = projectionMatrix * mv;
        // A mote is a few pixels across at arm's length, never more.
        gl_PointSize = uSize * (1.0 + vBright * 0.8) * (3.2 / max(-mv.z, 0.05));
      }
    `,
    fragmentShader: /* glsl */ `
      uniform vec3 uColor;
      varying float vBright;
      void main() {
        if (vBright < 0.004) discard;
        vec2 d = gl_PointCoord - 0.5;
        float r = dot(d, d);
        if (r > 0.25) discard;
        float soft = 1.0 - smoothstep(0.0, 0.25, r);
        gl_FragColor = vec4(uColor * vBright * soft * 0.85, 1.0);
      }
    `,
  });

  const points = new THREE.Points(geometry, material);
  points.frustumCulled = true;
  points.renderOrder = 4;
  points.userData.ignoreRaycast = true;
  points.userData.noMerge = true;
  points.visible = false;
  scene.add(points);

  const _dir = new THREE.Vector3();
  const _origin = new THREE.Vector3();

  return {
    points,
    /** Centre the volume between the lamp head and where its beam lands. */
    place(head: THREE.Object3D, pool: THREE.Vector3) {
      head.getWorldPosition(_origin);
      uniforms.uOrigin.value.copy(_origin);
      uniforms.uCenter.value.copy(_origin).lerp(pool, 0.45);
      uniforms.uDir.value.copy(pool).sub(_origin).normalize();
      points.position.set(0, 0, 0);
      geometry.boundingSphere!.center.copy(uniforms.uCenter.value);
    },
    /** `intensity` is the lamp's own level; at zero the cloud is not drawn at all. */
    update(time: number, intensity: number, coneCos: number) {
      const lit = intensity > 0.04;
      points.visible = lit;
      if (!lit) return;
      uniforms.uTime.value = time;
      uniforms.uIntensity.value = Math.min(1, intensity * 0.24);
      uniforms.uCos.value = coneCos;
      void _dir;
    },
  };
}
