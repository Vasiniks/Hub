import * as THREE from 'three';

/**
 * The street outside the `?v2` window: four baked panorama layers instead of ~390k triangles.
 *
 * `blender/scripts/v2_exterior_web.py` renders `NEW_exterior` in Cycles (the approved dusk
 * setup) as equirectangular panoramas from one bake eye — the midpoint of the seated and
 * standing eyes — one per depth layer (far: ground + back rows + sky, opaque; mid: the houses
 * across the street; street: hydro poles, wires, street maples, parked sedan; near: the young
 * maples). Each layer here is a few triangles at that layer's real depth (a ground disc +
 * cylinder wall, three vertical planes). The
 * fragment shader projects the fragment's world position back to the bake eye and reads the
 * panorama there, so anything that really lies on its proxy is exact from any viewpoint and the
 * rest parallaxes approximately — the seated↔standing move slides the layers past each other.
 *
 * Grade: texels are scene-linear radiance (log2-encoded, 8 bits), written straight into the HDR
 * scene buffer — emissive, unlit — so the room's AgX output pass and its 2^0.45 exposure grade
 * the street exactly like the baked room. Nothing here is lit, nothing lights anything.
 *
 * Drawing: painter's order far → mid → street → near (sidecar order), all after the opaque room (transparent queue,
 * renderOrder), depth-tested against the room so only the window shows them, never writing
 * depth. Every vertex is pushed onto the far plane (skybox trick), so the 55 m proxies are never
 * clipped by the room camera's far plane and never occlude anything.
 */

interface LayerSpec {
  name: 'far' | 'mid' | 'street' | 'near';
  file: string;
  size: [number, number];
  /** Panorama extent in degrees, from the bake eye: azimuth (+ = right of -Z) and elevation. */
  lon: [number, number];
  lat: [number, number];
  opaque: boolean;
  proxy:
    | { type: 'disc+cylinder'; center: [number, number]; groundY: number; radius: number; top: number }
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
uniform int proxyType; // 0: plane z = proxy.x; 1: ground disc y = proxy.z (centre proxy.xy in xz, radius proxy.w) + wall
uniform vec4 proxy;
uniform vec2 glass;    // plane z, IOR (<= 1: no glass)
varying vec3 vWorld;

vec3 hitProxy(vec3 o, vec3 d) {
  if (proxyType == 0) return o + d * ((proxy.x - o.z) / d.z);
  if (d.y < 0.0) {
    vec3 p = o + d * ((proxy.z - o.y) / d.y);
    if (length(p.xz - proxy.xy) <= proxy.w) return p;
  }
  vec2 oc = o.xz - proxy.xy;
  float a = dot(d.xz, d.xz);
  float b = 2.0 * dot(oc, d.xz);
  float c = dot(oc, oc) - proxy.w * proxy.w;
  return o + d * ((-b + sqrt(max(b * b - 4.0 * a * c, 0.0))) / (2.0 * a));
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
  // Ground disc (fan) + cylinder wall around the bake eye.
  const n = 64;
  const [cx, cz] = p.center;
  const pos: number[] = [cx, p.groundY, cz];
  const idx: number[] = [];
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * Math.PI * 2;
    const x = cx + p.radius * Math.sin(a);
    const z = cz - p.radius * Math.cos(a);
    pos.push(x, p.groundY, z, x, p.top, z);
  }
  for (let i = 0; i < n; i++) {
    const r0 = 1 + i * 2;
    const r1 = 1 + (i + 1) * 2;
    idx.push(0, r1, r0); // disc
    idx.push(r0, r1, r1 + 1, r0, r1 + 1, r0 + 1); // wall
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setIndex(idx);
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
              : new THREE.Vector4(spec.proxy.center[0], spec.proxy.center[1], spec.proxy.groundY, spec.proxy.radius),
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
