import * as THREE from 'three';

/**
 * What the window looks onto: a sky with a sun, and two hazy bands of distant
 * roofline/treeline for aerial depth. It sits outside the set and is only seen
 * through the window; walls occlude it everywhere else.
 */
export interface ExteriorState {
  zenith: THREE.Color;
  horizon: THREE.Color;
  ground: THREE.Color;
  sunDirection: THREE.Vector3;
  sunColor: THREE.Color;
  sunVisible: number;
  /** 0 by day, 1 deep at night: drives the lit windows across the skyline. */
  night: number;
}

function silhouette(width: number, base: number, amp: number, seed: number, steps: number) {
  const shape = new THREE.Shape();
  shape.moveTo(-width / 2, -2);
  let s = seed;
  const r = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i <= steps; i++) {
    const x = -width / 2 + (i / steps) * width;
    // Mix of blocky rooflines and softer tree crowns.
    const roof = r() > 0.55 ? Math.round(r() * 3) * amp * 0.35 : 0;
    const crown = Math.sin(i * 0.9 + seed) * amp * 0.25 + r() * amp * 0.4;
    const y = base + Math.max(roof, crown);
    shape.lineTo(x, y);
    shape.lineTo(x + width / steps, y);
  }
  shape.lineTo(width / 2, -2);
  shape.closePath();
  return new THREE.ShapeGeometry(shape);
}

/**
 * §10: the skyline keeps a little life after dark. Scattered lit windows across the two
 * silhouette bands, as one additive point cloud that fades out completely by day — so the
 * night window has something to look at without brightening the room.
 */
function cityLights(bands: { z: number; width: number; top: number; count: number; seed: number }[]) {
  const total = bands.reduce((n, b) => n + b.count, 0);
  const positions = new Float32Array(total * 3);
  const shades = new Float32Array(total);
  let i = 0;
  for (const band of bands) {
    let s = band.seed;
    const r = () => ((s = (s * 16807) % 2147483647) / 2147483647);
    for (let n = 0; n < band.count; n++) {
      // Quantised to a loose grid so they read as windows rather than as stars.
      positions[i * 3] = Math.round((r() - 0.5) * band.width * 6) / 6;
      positions[i * 3 + 1] = 0.12 + Math.round(r() * band.top * 12) / 12;
      positions[i * 3 + 2] = band.z;
      shades[i] = 0.35 + r() * 0.65;
      i++;
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('shade', new THREE.BufferAttribute(shades, 1));
  const uniforms = { uNight: { value: 0 } };
  const material = new THREE.ShaderMaterial({
    uniforms,
    fog: false,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    vertexShader: /* glsl */ `
      attribute float shade;
      uniform float uNight;
      varying float vShade;
      void main() {
        vShade = shade * uNight;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        gl_Position = projectionMatrix * mv;
        gl_PointSize = max(1.5, 26.0 / max(-mv.z, 0.05));
      }
    `,
    fragmentShader: /* glsl */ `
      varying float vShade;
      void main() {
        if (vShade < 0.01) discard;
        vec2 d = gl_PointCoord - 0.5;
        if (max(abs(d.x), abs(d.y)) > 0.4) discard;
        // Warm interiors with a few cooler ones mixed in.
        vec3 warm = mix(vec3(0.55, 0.72, 1.0), vec3(1.0, 0.82, 0.55), step(0.55, vShade));
        gl_FragColor = vec4(warm * vShade * 0.7, 1.0);
      }
    `,
  });
  const points = new THREE.Points(geometry, material);
  points.userData.ignoreRaycast = true;
  points.userData.noMerge = true;
  points.frustumCulled = false;
  return { points, uniforms };
}

export function createExterior(scene: THREE.Scene, observer: THREE.Vector3) {
  const group = new THREE.Group();
  group.name = 'exterior';

  const uniforms = {
    uObserver: { value: observer.clone() },
    uZenith: { value: new THREE.Color() },
    uHorizon: { value: new THREE.Color() },
    uGround: { value: new THREE.Color() },
    uSunDir: { value: new THREE.Vector3(0, 1, -1).normalize() },
    uSunColor: { value: new THREE.Color() },
    uSunVisible: { value: 1 },
  };

  const skyMaterial = new THREE.ShaderMaterial({
    uniforms,
    fog: false,
    depthWrite: true,
    vertexShader: /* glsl */ `
      varying vec3 vWorld;
      void main() {
        vec4 w = modelMatrix * vec4(position, 1.0);
        vWorld = w.xyz;
        gl_Position = projectionMatrix * viewMatrix * w;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform vec3 uObserver, uZenith, uHorizon, uGround, uSunDir, uSunColor;
      uniform float uSunVisible;
      varying vec3 vWorld;
      void main() {
        vec3 d = normalize(vWorld - uObserver);
        float up = smoothstep(-0.02, 0.55, d.y);
        vec3 sky = mix(uHorizon, uZenith, pow(up, 0.6));
        sky = mix(sky, uGround, smoothstep(0.0, -0.3, d.y));
        float s = max(dot(d, uSunDir), 0.0);
        sky += uSunColor * uSunVisible * (pow(s, 1800.0) * 60.0 + pow(s, 90.0) * 1.3 + pow(s, 10.0) * 0.14);
        gl_FragColor = vec4(sky, 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }
    `,
  });
  const sky = new THREE.Mesh(new THREE.PlaneGeometry(16, 10), skyMaterial);
  sky.position.set(-0.3, 2.0, -5.2);
  group.add(sky);

  const farMat = new THREE.MeshBasicMaterial({ color: '#8a96a3', fog: false });
  const nearMat = new THREE.MeshBasicMaterial({ color: '#6c7784', fog: false });
  const far = new THREE.Mesh(silhouette(14, 0.95, 0.9, 11, 46), farMat);
  far.position.set(-0.3, 0, -4.9);
  const near = new THREE.Mesh(silhouette(11, 0.55, 0.8, 5, 30), nearMat);
  near.position.set(-0.3, 0, -3.9);
  group.add(far, near);

  const lights = cityLights([
    { z: -4.88, width: 13, top: 1.5, count: 150, seed: 31 },
    { z: -3.88, width: 10, top: 1.1, count: 90, seed: 77 },
  ]);
  lights.points.position.set(-0.3, 0, 0);
  group.add(lights.points);

  for (const m of [sky, far, near]) {
    m.castShadow = false;
    m.receiveShadow = false;
    m.userData.noMerge = true;
  }
  scene.add(group);

  const _haze = new THREE.Color();
  return {
    group,
    update(state: ExteriorState) {
      uniforms.uZenith.value.copy(state.zenith);
      uniforms.uHorizon.value.copy(state.horizon);
      uniforms.uGround.value.copy(state.ground);
      uniforms.uSunDir.value.copy(state.sunDirection);
      uniforms.uSunColor.value.copy(state.sunColor);
      uniforms.uSunVisible.value = state.sunVisible;
      // Aerial perspective: distant layers dissolve toward the horizon colour.
      farMat.color.copy(_haze.copy(state.horizon).lerp(state.ground, 0.35));
      nearMat.color.copy(_haze.copy(state.horizon).lerp(state.ground, 0.62));
      lights.uniforms.uNight.value = state.night;
    },
  };
}
