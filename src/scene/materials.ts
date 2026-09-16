import * as THREE from 'three';

/** Small procedural canvas textures: cheap surface variation for low-poly meshes. */
function canvasTexture(size: number, paint: (ctx: CanvasRenderingContext2D, s: number) => void, srgb = true) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  paint(ctx, size);
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = 8;
  if (srgb) tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function rand(seed: number) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
}

function woodTexture() {
  return canvasTexture(1024, (ctx, s) => {
    const r = rand(7);
    ctx.fillStyle = '#6b4f3a';
    ctx.fillRect(0, 0, s, s);
    for (let i = 0; i < 260; i++) {
      const y = r() * s;
      const light = r() > 0.5;
      ctx.strokeStyle = light ? `rgba(160,120,86,${0.05 + r() * 0.12})` : `rgba(40,26,18,${0.05 + r() * 0.14})`;
      ctx.lineWidth = 1 + r() * 5;
      ctx.beginPath();
      ctx.moveTo(0, y);
      for (let x = 0; x <= s; x += 64) ctx.lineTo(x, y + Math.sin(x * 0.004 + i) * 6 * r());
      ctx.stroke();
    }
  });
}

function roughnessNoise(base: number, spread: number, seed: number) {
  return canvasTexture(
    512,
    (ctx, s) => {
      const r = rand(seed);
      const img = ctx.createImageData(s, s);
      for (let i = 0; i < img.data.length; i += 4) {
        const v = Math.max(0, Math.min(255, (base + (r() - 0.5) * spread) * 255));
        img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
        img.data[i + 3] = 255;
      }
      ctx.putImageData(img, 0, 0);
      ctx.globalAlpha = 0.35;
      ctx.filter = 'blur(6px)';
      ctx.drawImage(ctx.canvas, 0, 0);
    },
    false,
  );
}

export type Materials = ReturnType<typeof createMaterials>;

/** Colour of the void the set dissolves into; kept equal to background and fog. */
export const fadeColor = new THREE.Color('#0f1216');

type Range = [number, number];
const OFF: Range = [1e5, 1e5 + 1];

function applySetFade(mat: THREE.Material, o: { center?: [number, number]; radial?: Range; x?: Range; z?: Range; y?: Range }) {
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uFadeColor = { value: fadeColor };
    shader.uniforms.uFadeCenter = { value: new THREE.Vector2(...(o.center ?? [0, 0])) };
    shader.uniforms.uFadeR = { value: new THREE.Vector2(...(o.radial ?? OFF)) };
    shader.uniforms.uFadeX = { value: new THREE.Vector2(...(o.x ?? OFF)) };
    shader.uniforms.uFadeZ = { value: new THREE.Vector2(...(o.z ?? OFF)) };
    shader.uniforms.uFadeY = { value: new THREE.Vector2(...(o.y ?? OFF)) };
    shader.vertexShader =
      'varying vec3 vSetWorld;\n' +
      shader.vertexShader.replace(
        '#include <project_vertex>',
        '#include <project_vertex>\n  vSetWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;',
      );
    shader.fragmentShader =
      'uniform vec3 uFadeColor;\nuniform vec2 uFadeCenter;\nuniform vec2 uFadeR;\nuniform vec2 uFadeX;\nuniform vec2 uFadeZ;\nuniform vec2 uFadeY;\nvarying vec3 vSetWorld;\n' +
      shader.fragmentShader.replace(
        '#include <fog_fragment>',
        `#include <fog_fragment>
  float setFade = smoothstep(uFadeR.x, uFadeR.y, distance(vSetWorld.xz, uFadeCenter));
  setFade = max(setFade, smoothstep(uFadeX.x, uFadeX.y, vSetWorld.x));
  setFade = max(setFade, smoothstep(uFadeZ.x, uFadeZ.y, vSetWorld.z));
  setFade = max(setFade, smoothstep(uFadeY.x, uFadeY.y, vSetWorld.y));
  gl_FragColor.rgb = mix(gl_FragColor.rgb, uFadeColor, setFade);`,
      );
  };
}

export function createMaterials() {
  const wood = woodTexture();
  wood.repeat.set(1, 1);
  const floorRough = roughnessNoise(0.55, 0.5, 3);
  floorRough.repeat.set(3, 3);

  const floor = new THREE.MeshStandardMaterial({
    color: '#8f9296',
    roughness: 0.5,
    roughnessMap: floorRough,
    metalness: 0,
  });
  applySetFade(floor, { center: [-0.15, -0.35], radial: [1.9, 4.0] });
  const wall = new THREE.MeshStandardMaterial({ color: '#bdc0c3', roughness: 0.92 });
  applySetFade(wall, { x: [1.35, 2.4], z: [0.45, 1.28], y: [2.6, 3.3] });

  return {
    deskTop: new THREE.MeshPhysicalMaterial({
      map: wood,
      roughness: 0.42,
      clearcoat: 0.35,
      clearcoatRoughness: 0.35,
    }),
    steel: new THREE.MeshStandardMaterial({ color: '#2a2d31', roughness: 0.42, metalness: 0.85 }),
    aluminum: new THREE.MeshStandardMaterial({ color: '#b9bec4', roughness: 0.32, metalness: 1 }),
    plasticBlack: new THREE.MeshStandardMaterial({ color: '#16181b', roughness: 0.55 }),
    plasticGrey: new THREE.MeshStandardMaterial({ color: '#3b3f45', roughness: 0.6 }),
    plasticWhite: new THREE.MeshStandardMaterial({ color: '#d7d9dc', roughness: 0.5 }),
    fabric: new THREE.MeshStandardMaterial({ color: '#24272c', roughness: 0.95 }),
    rubber: new THREE.MeshStandardMaterial({ color: '#0e0f11', roughness: 0.9 }),
    wall,
    floor,
    rug: new THREE.MeshStandardMaterial({ color: '#34373b', roughness: 1 }),
    paper: new THREE.MeshStandardMaterial({ color: '#e6e4df', roughness: 0.85 }),
    cardboard: new THREE.MeshStandardMaterial({ color: '#9a7b58', roughness: 0.9 }),
    pcb: new THREE.MeshStandardMaterial({ color: '#12301f', roughness: 0.45, metalness: 0.2 }),
    bumperRed: new THREE.MeshStandardMaterial({ color: '#a3262a', roughness: 0.85 }),
    safetyOrange: new THREE.MeshStandardMaterial({ color: '#e2661a', roughness: 0.5 }),
    // No transmission: it would add a full scene render every frame for a sliver of tinted glass.
    glass: new THREE.MeshStandardMaterial({
      color: '#aab4bd',
      roughness: 0.08,
      transparent: true,
      opacity: 0.22,
      depthWrite: false,
    }),
    windowGlass: new THREE.MeshStandardMaterial({
      color: '#c9d4dc',
      roughness: 0.04,
      metalness: 0,
      transparent: true,
      opacity: 0.08,
      depthWrite: false,
    }),
    windowFrame: new THREE.MeshStandardMaterial({ color: '#25282c', roughness: 0.5, metalness: 0.55 }),
    sill: new THREE.MeshStandardMaterial({ color: '#d4d5d6', roughness: 0.45 }),
    ledWhite: new THREE.MeshStandardMaterial({ color: '#000000', emissive: '#f3f6ff', emissiveIntensity: 3 }),
    ledGreen: new THREE.MeshStandardMaterial({ color: '#000000', emissive: '#6dffa8', emissiveIntensity: 2.5 }),
    ledOrange: new THREE.MeshStandardMaterial({ color: '#000000', emissive: '#ff8a2a', emissiveIntensity: 3 }),
  };
}
