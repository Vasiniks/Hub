import * as THREE from 'three';
import { projectMaps, type SurfaceTextures } from './textures';

/**
 * Materials carry most of the perceived quality here: the geometry stays low-poly, so what
 * separates the desk from the MacBook from a parts bin is how each one answers the light.
 *
 * Textures are small procedural canvases (256–512px). They exist to break up flat colour and
 * to vary roughness across a surface, never to add detail that geometry should be carrying.
 */
function canvasTexture(size: number, paint: (ctx: CanvasRenderingContext2D, s: number) => void, srgb = true) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  paint(ctx, size);
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = 4;
  if (srgb) tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function rand(seed: number) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
}

/** Greyscale noise for roughness maps: `base` is the mean, `spread` the peak-to-peak variation. */
function roughnessNoise(base: number, spread: number, seed: number, size = 256, blur = 6) {
  return canvasTexture(
    size,
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
      ctx.filter = `blur(${blur}px)`;
      ctx.drawImage(ctx.canvas, 0, 0);
    },
    false,
  );
}

/** Fine directional streaks: reads as brushed aluminium once it drives roughness. */
function brushedNoise(seed: number) {
  return canvasTexture(
    256,
    (ctx, s) => {
      const r = rand(seed);
      ctx.fillStyle = '#6e6e6e';
      ctx.fillRect(0, 0, s, s);
      for (let i = 0; i < 900; i++) {
        const y = r() * s;
        const v = Math.round(90 + r() * 90);
        ctx.strokeStyle = `rgba(${v},${v},${v},0.5)`;
        ctx.lineWidth = r() * 1.4;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(s, y + (r() - 0.5) * 3);
        ctx.stroke();
      }
    },
    false,
  );
}

/** Pale oak: warm floor tone that the lamp can pick up at night. */
/** Board with a solder mask, traces and pads: PCBs should not read as green boxes. */
function pcbTexture(base: string, seed: number) {
  return canvasTexture(256, (ctx, s) => {
    const r = rand(seed);
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, s, s);
    ctx.lineCap = 'round';
    for (let i = 0; i < 70; i++) {
      ctx.strokeStyle = `rgba(214,182,96,${0.18 + r() * 0.28})`;
      ctx.lineWidth = 1 + r() * 1.6;
      let x = r() * s;
      let y = r() * s;
      ctx.beginPath();
      ctx.moveTo(x, y);
      for (let seg = 0; seg < 3; seg++) {
        const horizontal = r() > 0.5;
        x += horizontal ? (r() - 0.5) * 90 : 0;
        y += horizontal ? 0 : (r() - 0.5) * 90;
        ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    for (let i = 0; i < 120; i++) {
      ctx.beginPath();
      ctx.arc(r() * s, r() * s, 1.4 + r() * 1.8, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(226,198,120,${0.4 + r() * 0.4})`;
      ctx.fill();
    }
  });
}

export type Materials = ReturnType<typeof createMaterials>;

/** Colour the set dissolves into; kept equal to the background and the fog. */
export const fadeColor = new THREE.Color('#0f1216');

/**
 * Shade from the environment probe and ambient terms only, skipping every direct light.
 *
 * For the window pane: a transparent surface covering a third of the seated view, whose look is
 * its reflection and tint. The sun and the window's area light sit behind it, the monitor and
 * shelf face away from it, and the lamp already appears in it through the probe (its diffuser is
 * in the capture) — so the direct-light loops were ~0.5 ms of shading that contributed nothing
 * visible. `?glass=full` restores them.
 */
function imageLightingOnly<T extends THREE.MeshStandardMaterial>(mat: T): T {
  if (new URLSearchParams(location.search).get('glass') === 'full') return mat;
  mat.onBeforeCompile = (shader, renderer) => {
    Object.getPrototypeOf(mat).onBeforeCompile.call(mat, shader, renderer);
    const chunk = (THREE.ShaderChunk as unknown as Record<string, string>).lights_fragment_begin;
    const start = chunk.indexOf('#if ( NUM_POINT_LIGHTS > 0 ) && defined( RE_Direct )');
    const end = chunk.indexOf('#if defined( RE_IndirectDiffuse )');
    if (start < 0 || end < start) throw new Error('image lighting only: lights_fragment_begin changed');
    shader.fragmentShader = shader.fragmentShader.replace('#include <lights_fragment_begin>', chunk.slice(0, start) + chunk.slice(end));
  };
  mat.customProgramCacheKey = () => 'image-lighting-only';
  return mat;
}

type Range = [number, number];
const OFF: Range = [1e5, 1e5 + 1];

/**
 * Dissolve geometry into the background past a boundary, so the room reads as a designed set
 * rather than a model that stops. Distance fog handles depth; this handles the edges of the
 * floor and the far ends of the walls, which fog alone leaves as hard silhouettes.
 */
function applySetFade(mat: THREE.Material, o: { center?: [number, number]; radial?: Range; x?: Range; z?: Range; y?: Range }) {
  mat.onBeforeCompile = (shader, renderer) => {
    // The class-wide hook (split environment, areaLights.ts) is installed after materials exist.
    Object.getPrototypeOf(mat).onBeforeCompile.call(mat, shader, renderer);
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

const standard = (p: THREE.MeshStandardMaterialParameters) => new THREE.MeshStandardMaterial(p);

export function createMaterials(surfaces: SurfaceTextures) {
  const brushed = brushedNoise(23);
  brushed.repeat.set(3, 1);
  // The desk is the largest light-catching surface in the frame: its roughness has to vary or
  // the whole top reads as one flat value under the window.
  const paintRough = roughnessNoise(0.54, 0.16, 91, 256, 10);
  paintRough.repeat.set(2, 2);
  const binRough = roughnessNoise(0.6, 0.3, 17, 256, 4);

  // Scanned oak strip floor. The disc is 18 m across with 0–1 UVs, so twelve repeats puts one
  // texture tile at 1.5 m — the scale the boards were photographed at. The roughness map's
  // mean is 0.35; the factor scales it back to the floor's established ~0.62 response.
  for (const t of [surfaces.floorColor, surfaces.floorNormal, surfaces.floorRough]) t.repeat.set(12, 12);
  const floor = standard({
    map: surfaces.floorColor,
    normalMap: surfaces.floorNormal,
    normalScale: new THREE.Vector2(0.6, 0.6),
    roughness: 1.75,
    roughnessMap: surfaces.floorRough,
    metalness: 0,
    envMapIntensity: 0.5,
  });
  applySetFade(floor, { center: [-0.1, -0.4], radial: [2.3, 4.6] });
  // Painted plaster: surface relief and roughness only — the paint colour stays the room's.
  const wall = standard({
    color: '#94969a',
    roughness: 1.8,
    roughnessMap: surfaces.wallRough,
    normalMap: surfaces.wallNormal,
    normalScale: new THREE.Vector2(0.35, 0.35),
  });
  applySetFade(wall, { x: [2.3, 3.5], z: [0.55, 1.45], y: [2.7, 3.3] });
  projectMaps(wall, 1.6);
  const fabric = standard({
    color: '#24272c',
    roughness: 1.3,
    roughnessMap: surfaces.fabricRough,
    normalMap: surfaces.fabricNormal,
    normalScale: new THREE.Vector2(0.8, 0.8),
  });
  projectMaps(fabric, 0.09);
  // The rug reuses the fabric scan at a coarser tile: pile texture for no extra download.
  const rug = standard({
    color: '#33363a',
    roughness: 1.35,
    roughnessMap: surfaces.fabricRough,
    normalMap: surfaces.fabricNormal,
    normalScale: new THREE.Vector2(0.9, 0.9),
  });
  projectMaps(rug, 0.22);

  return {
    /** §2: a clean white tabletop. Diffuse, with only enough sheen to read as painted. */
    deskWhite: standard({ color: '#e9eaea', roughness: 0.52, roughnessMap: paintRough, metalness: 0, envMapIntensity: 0.55 }),
    deskEdge: standard({ color: '#dcdee0', roughness: 0.6, metalness: 0 }),
    steel: standard({ color: '#33373c', roughness: 0.44, metalness: 0.82 }),
    aluminum: standard({ color: '#b7bcc2', roughness: 0.3, roughnessMap: brushed, metalness: 1, envMapIntensity: 1 }),
    aluminumDark: standard({ color: '#4c5157', roughness: 0.42, roughnessMap: brushed, metalness: 1 }),
    plasticBlack: standard({ color: '#15171a', roughness: 0.52 }),
    plasticGrey: standard({ color: '#555b62', roughness: 0.62 }),
    plasticWhite: standard({ color: '#eceef0', roughness: 0.44, envMapIntensity: 0.45 }),
    keycap: standard({ color: '#e7e9eb', roughness: 0.56 }),
    keycapAccent: standard({ color: '#cfd3d8', roughness: 0.58 }),
    binBlue: standard({ color: '#aebdc8', roughness: 0.58, roughnessMap: binRough, envMapIntensity: 0.4 }),
    binWarm: standard({ color: '#c8c2b4', roughness: 0.64, roughnessMap: binRough, envMapIntensity: 0.4 }),
    pcbGreen: standard({ map: pcbTexture('#123322', 5), roughness: 0.42, metalness: 0.25 }),
    pcbBlue: standard({ map: pcbTexture('#11243c', 12), roughness: 0.42, metalness: 0.25 }),
    pcbBlack: standard({ map: pcbTexture('#14161a', 31), roughness: 0.46, metalness: 0.3 }),
    copper: standard({ color: '#b87333', roughness: 0.38, metalness: 1 }),
    gold: standard({ color: '#d8ad52', roughness: 0.26, metalness: 1 }),
    silver: standard({ color: '#c2c7cc', roughness: 0.28, metalness: 1 }),
    bronze: standard({ color: '#a2703f', roughness: 0.34, metalness: 1 }),
    ribbonBlue: standard({ color: '#2f4a7a', roughness: 0.88 }),
    ribbonRed: standard({ color: '#7d2b2f', roughness: 0.88 }),
    ribbonGreen: standard({ color: '#2f5f48', roughness: 0.88 }),
    fabric,
    rubber: standard({ color: '#0e0f11', roughness: 0.9 }),
    paper: standard({ color: '#e8e6e0', roughness: 0.88 }),
    /** Glazed ceramic: whiter and far glossier than the room's plastics. */
    ceramic: standard({ color: '#f1f0ec', roughness: 0.18, envMapIntensity: 0.7 }),
    cardboard: standard({ color: '#a98a64', roughness: 0.9 }),
    wall,
    floor,
    rug,
    safetyOrange: standard({ color: '#e2661a', roughness: 0.5 }),
    bumperRed: standard({ color: '#a3262a', roughness: 0.85 }),
    // No transmission anywhere: it costs a full extra scene render per frame, and at these
    // sizes a rough standard material with low opacity is indistinguishable.
    glass: standard({ color: '#aab4bd', roughness: 0.08, transparent: true, opacity: 0.22, depthWrite: false }),
    // Roughness 0.16, not 0.04: a pane that near-mirror turns every point source in the room
    // into a single blown-out pixel in the glass. Real glass at this scale reads as a soft
    // sheen, and the softer lobe is also what makes the night reflections believable.
    windowGlass: imageLightingOnly(
      standard({
        color: '#c9d4dc',
        roughness: 0.16,
        metalness: 0,
        transparent: true,
        opacity: 0.08,
        depthWrite: false,
      }),
    ),
    windowFrame: standard({ color: '#23262a', roughness: 0.5, metalness: 0.55 }),
    // A painted sill reflects about 70%, not 92%. At 92% it clipped under direct sun.
    sill: standard({ color: '#dcdedf', roughness: 0.56 }),
    ledWhite: standard({ color: '#000000', emissive: '#f3f6ff', emissiveIntensity: 3 }),
    ledGreen: standard({ color: '#000000', emissive: '#6dffa8', emissiveIntensity: 2.5 }),
    ledOrange: standard({ color: '#000000', emissive: '#ff8a2a', emissiveIntensity: 3 }),
    ledBlue: standard({ color: '#000000', emissive: '#5aa8ff', emissiveIntensity: 2.5 }),
  };
}
