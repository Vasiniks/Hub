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
        sky += uSunColor * uSunVisible * (pow(s, 1800.0) * 60.0 + pow(s, 64.0) * 1.6 + pow(s, 6.0) * 0.25);
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
    },
  };
}
