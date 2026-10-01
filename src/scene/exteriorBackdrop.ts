import * as THREE from 'three';

/**
 * The street outside the `?v2` window: two baked panorama cards instead of ~390k triangles.
 *
 * `blender/scripts/v2_exterior_web.py` renders `NEW_exterior` in Cycles (the approved dusk
 * setup) as equirectangular panoramas from one bake eye — the midpoint of the seated and
 * standing eyes — one per card: `back` (opaque: road and lawns on a ground plane, then the
 * houses across the street, back-row trees and sky on a wall at the house fronts) and `front`
 * (alpha: hydro poles, wires, street maples, the young maples in front, on one vertical plane).
 * The fragment shader projects the fragment's world position back to the bake eye and reads the
 * panorama there, so anything that really lies on its card is exact from any viewpoint and the
 * rest parallaxes approximately — the seated↔standing move slides the cards past each other.
 * Two cards, not more: each is a full-window fragment layer, and the site must run on low-end
 * GPUs. No extra render pass: both draw inside the scene pass.
 *
 * Grade: texels are scene-linear radiance (log2-encoded, 8 bits), written straight into the HDR
 * scene buffer — emissive, unlit — so the room's AgX output pass and its 2^0.45 exposure grade
 * the street exactly like the baked room. Nothing here is lit, nothing lights anything.
 *
 * Drawing: painter's order back → front (sidecar order), all after the opaque room (transparent queue,
 * renderOrder), depth-tested against the room so only the window shows them, never writing
 * depth. Every vertex is pushed onto the far plane (skybox trick), so the 55 m proxies are never
 * clipped by the room camera's far plane and never occlude anything.
 */

interface LayerSpec {
  name: 'back' | 'front';
  file: string;
  size: [number, number];
  /** Panorama extent in degrees, from the bake eye: azimuth (+ = right of -Z) and elevation. */
  lon: [number, number];
  lat: [number, number];
  opaque: boolean;
  proxy:
    | { type: 'ground+wall'; groundY: number; wallZ: number; nearZ: number; x: [number, number]; top: number }
    | { type: 'planeZ'; z: number; x: [number, number]; y: [number, number] };
}

interface Sidecar {
  /** Bake eye in three.js world coordinates. */
  eye: [number, number, number];
  encoding: { type: 'log2'; min: number; max: number };
  /** The window glass the approved stills were rendered through (see `glass` uniform). */
  glass: { plane_z: number; ior: number };
  /** Back to front. */
  layers: LayerSpec[];
}

export interface ExteriorBackdrop {
  group: THREE.Group;
  tris: number;
  /** Bytes of the texture files as fetched (compressed). */
  bytes: number;
  /**
   * 1.5 (sidecar default) reproduces the approved Cycles framing, seen through the scene's
   * refracting glass plane (~1.5x magnified street); 1 shows the street through plain air.
   */
  setGlassIor(ior: number): void;
}

const vertexShader = /* glsl */ `
varying vec3 vWorld;
void main() {
  vec4 world = modelMatrix * vec4(position, 1.0);
  vWorld = world.xyz;
  gl_Position = projectionMatrix * viewMatrix * world;
  // On the far plane: never clipped by it, always behind the room.
  gl_Position.z = gl_Position.w * 0.999999;
}`;

const fragmentShader = /* glsl */ `
uniform sampler2D map;
uniform vec3 eye;
uniform vec4 range;    // lon0, lon1, lat0, lat1 (radians)
uniform vec2 logRange; // log2 min, max
uniform float opaque;
uniform int proxyType; // 0: plane z = proxy.x; 1: ground y = proxy.y in front of the wall z = proxy.x
uniform vec4 proxy;
uniform vec2 glass;    // plane z, IOR (<= 1: no glass)
varying vec3 vWorld;

vec3 hitProxy(vec3 o, vec3 d) {
  if (proxyType == 1 && d.y < 0.0) {
    vec3 p = o + d * ((proxy.y - o.y) / d.y);
    if (p.z >= proxy.x) return p;
  }
  return o + d * ((proxy.x - o.z) / d.z);
}

void main() {
  vec3 p = vWorld;
  float transmit = 1.0;
  if (glass.y > 1.0) {
    // The approved Cycles stills look through a single refracting glass plane (Mesh_11: IOR 1.5,
    // not thin-walled), which bends every view ray once: trace the refracted ray to this proxy.
    vec3 d = normalize(vWorld - cameraPosition);
    vec3 g = cameraPosition + d * ((glass.x - cameraPosition.z) / d.z);
    p = hitProxy(g, refract(d, vec3(0.0, 0.0, 1.0), 1.0 / glass.y));
    float f0 = pow((glass.y - 1.0) / (glass.y + 1.0), 2.0);
    transmit = 1.0 - (f0 + (1.0 - f0) * pow(1.0 - abs(d.z), 5.0));
  }
  vec3 d = normalize(p - eye);
  // three (x, y, z) = Blender (x, z, -y): azimuth atan(x, forward) with forward = -z.
  float az = atan(d.x, -d.z);
  float el = asin(clamp(d.y, -1.0, 1.0));
  vec2 uv = vec2((az - range.x) / (range.y - range.x), (el - range.z) / (range.w - range.z));
  vec4 t = texture2D(map, clamp(uv, 0.0, 1.0));
  vec3 radiance = exp2(logRange.x + t.rgb * (logRange.y - logRange.x)) * step(vec3(0.5 / 255.0), t.rgb);
  float inside = step(0.0, uv.x) * step(uv.x, 1.0) * step(0.0, uv.y) * step(uv.y, 1.0);
  float a = opaque > 0.5 ? 1.0 : t.a * inside;
  // Premultiplied: blended with ONE, ONE_MINUS_SRC_ALPHA.
  gl_FragColor = vec4(radiance * transmit * a, a);
}`;

function proxyGeometry(spec: LayerSpec): THREE.BufferGeometry {
  const p = spec.proxy;
  if (p.type === 'planeZ') {
    const [x0, x1] = p.x;
    const [y0, y1] = p.y;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute([x0, y0, p.z, x1, y0, p.z, x1, y1, p.z, x0, y1, p.z], 3));
    g.setIndex([0, 1, 2, 0, 2, 3]);
    return g;
  }
  // Ground quad from the window out to the wall, then the wall up to `top`.
  const [x0, x1] = p.x;
  const { groundY: gy, wallZ: wz, nearZ: nz, top } = p;
  const g = new THREE.BufferGeometry();
  g.setAttribute(
    'position',
    new THREE.Float32BufferAttribute([x0, gy, nz, x1, gy, nz, x1, gy, wz, x0, gy, wz, x0, top, wz, x1, top, wz], 3),
  );
  g.setIndex([0, 2, 1, 0, 3, 2, 3, 5, 2, 3, 4, 5]);
  return g;
}

async function loadLayerTexture(url: string): Promise<{ tex: THREE.Texture; bytes: number }> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`exterior: ${url} ${res.status}`);
  const blob = await res.blob();
  // Straight alpha, data not colour: no premultiply, no colour-space conversion.
  const bitmap = await createImageBitmap(blob, { premultiplyAlpha: 'none', colorSpaceConversion: 'none', imageOrientation: 'flipY' });
  const tex = new THREE.Texture(bitmap);
  tex.flipY = false; // already flipped by createImageBitmap: uv.y = 0 is the bottom row (lowest elevation)
  tex.colorSpace = THREE.NoColorSpace;
  tex.premultiplyAlpha = false;
  tex.magFilter = THREE.LinearFilter;
  tex.minFilter = THREE.LinearFilter;
  tex.generateMipmaps = false;
  tex.wrapS = tex.wrapT = THREE.ClampToEdgeWrapping;
  tex.needsUpdate = true;
  return { tex, bytes: blob.size };
}

/** Loads `<base>exterior.json` and its layer images; add `group` to the `?v2` scene. */
export async function loadExteriorBackdrop(base: string): Promise<ExteriorBackdrop> {
  const res = await fetch(`${base}exterior.json`);
  if (!res.ok) throw new Error(`exterior sidecar missing at ${base}exterior.json`);
  const side = (await res.json()) as Sidecar;
  const group = new THREE.Group();
  group.name = 'exteriorBackdrop';
  const eye = new THREE.Vector3().fromArray(side.eye);
  const deg = Math.PI / 180;
  // Shared by every layer's material.
  const glass = new THREE.Vector2(side.glass.plane_z, side.glass.ior);
  let tris = 0;
  let bytes = 0;
  const layers = await Promise.all(side.layers.map(async (spec) => ({ spec, ...(await loadLayerTexture(base + spec.file)) })));
  for (const [i, { spec, tex, bytes: b }] of layers.entries()) {
    bytes += b;
    const mat = new THREE.ShaderMaterial({
      name: `exterior:${spec.name}`,
      vertexShader,
      fragmentShader,
      uniforms: {
        map: { value: tex },
        eye: { value: eye },
        range: { value: new THREE.Vector4(spec.lon[0] * deg, spec.lon[1] * deg, spec.lat[0] * deg, spec.lat[1] * deg) },
        logRange: { value: new THREE.Vector2(side.encoding.min, side.encoding.max) },
        opaque: { value: spec.opaque ? 1 : 0 },
        proxyType: { value: spec.proxy.type === 'planeZ' ? 0 : 1 },
        proxy: {
          value:
            spec.proxy.type === 'planeZ'
              ? new THREE.Vector4(spec.proxy.z, 0, 0, 0)
              : new THREE.Vector4(spec.proxy.wallZ, spec.proxy.groundY, 0, 0),
        },
        glass: { value: glass },
      },
      transparent: true,
      premultipliedAlpha: true,
      blending: THREE.NormalBlending,
      depthTest: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      fog: false,
      toneMapped: false,
    });
    const geo = proxyGeometry(spec);
    tris += geo.getIndex()!.count / 3;
    const mesh = new THREE.Mesh(geo, mat);
    mesh.name = `exterior:${spec.name}`;
    mesh.renderOrder = 1 + i; // painter's order, after the opaque room
    mesh.frustumCulled = false;
    mesh.matrixAutoUpdate = false;
    group.add(mesh);
  }
  return { group, tris, bytes, setGlassIor: (ior: number) => void (glass.y = ior) };
}
