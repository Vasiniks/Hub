// v2 props: build public/assets/v2/props/manifest.json and CREDITS.json from the shipped GLBs
// and the sidecars blender/scripts/v2_export_web.py wrote next to them.
// Usage: node scripts/props-manifest.mjs            (after optimize-glb.mjs has copied the sidecars)
// Triangle counts, byte sizes, emissive primitives and texture formats are read from the GLBs
// themselves, not trusted from the sidecars.
import fs from 'node:fs';
import path from 'node:path';
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';

const dir = process.env.PROPS_DST ?? 'public/assets/v2/props';
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);

// CC BY 4.0 assets that need a visible credit wherever they ship (assets/MANIFEST.md).
const CREDITS = {
  teto_plush: {
    title: 'Kasane Teto fatass plush', author: 'revsworks', licence: 'CC BY 4.0',
    url: 'https://sketchfab.com/3d-models/kasane-teto-fatass-plush-bd8157eb42a04161b2628e58dfd2a852',
  },
  mx_master_3s: {
    title: 'Mouse Logitech MX Master 3S white', author: 'Guibazilla', licence: 'CC BY 4.0',
    url: 'https://sketchfab.com/3d-models/mouse-logitech-mx-master-3s-white-dc82de97cbe64c6a8deae3328208c984',
  },
  bambu_a1_mini: {
    title: '3D Printer - Bambu Lab A1 Mini', author: 'neilvfx', licence: 'CC BY 4.0',
    url: 'https://sketchfab.com/3d-models/3d-printer-bambu-lab-a1-mini-407fb64c44be4e1888db246b447f811b',
  },
  motherboard: {
    title: 'MotherBoard + Components', author: 'Daniel Cardona', licence: 'CC BY 4.0',
    url: 'https://sketchfab.com/3d-models/motherboard-components-3bc94057328243d4b341a55f59160f8a',
  },
};
for (const c of Object.values(CREDITS)) {
  c.line = `"${c.title}" by ${c.author}, licensed under ${c.licence} (${c.url})`;
}

const assets = [];
let totalBytes = 0;
let totalTris = 0;
for (const f of fs.readdirSync(dir).filter((x) => x.endsWith('.glb')).sort()) {
  const name = path.basename(f, '.glb');
  const file = path.join(dir, f);
  const doc = await io.read(file);
  const root = doc.getRoot();
  let tris = 0;
  const emissive = [];
  for (const node of root.listNodes()) {
    const mesh = node.getMesh();
    if (!mesh) continue;
    for (const prim of mesh.listPrimitives()) {
      const idx = prim.getIndices();
      const n = idx ? idx.getCount() : prim.getAttribute('POSITION').getCount();
      tris += n / 3;
      const m = prim.getMaterial();
      if (!m) continue;
      const ef = m.getEmissiveFactor();
      if (m.getEmissiveTexture() || ef.some((v) => v > 0)) {
        const strength = m.getExtension('KHR_materials_emissive_strength');
        emissive.push({ node: node.getName(), material: m.getName(),
          emissiveFactor: ef.map((v) => +v.toFixed(4)),
          emissiveStrength: strength ? +strength.getEmissiveStrength().toFixed(3) : 1,
          textured: !!m.getEmissiveTexture() });
      }
    }
  }
  const materials = root.listMaterials().map((m) => {
    const unlit = !!m.getExtension('KHR_materials_unlit');
    const ef = m.getEmissiveFactor();
    const emissive = !!m.getEmissiveTexture() || ef.some((v) => v > 0);
    return {
      name: m.getName(),
      mode: unlit ? 'lit' : 'pbr',
      ...(unlit ? { litScale: +(+(m.getExtras()?.litScale ?? 1)).toPrecision(6) } : {}),
      doubleSided: m.getDoubleSided(),
      ...(emissive ? { emissive: true } : {}),
      alphaMode: m.getAlphaMode(),
      textures: [m.getBaseColorTexture() && 'baseColor', m.getMetallicRoughnessTexture() && 'ORM',
        m.getNormalTexture() && 'normal', m.getEmissiveTexture() && 'emissive'].filter(Boolean),
    };
  });
  const textures = root.listTextures().map((t) => ({ name: t.getName(), mime: t.getMimeType(),
    size: t.getSize(), bytes: t.getImage()?.byteLength ?? 0 }));
  const sidecar = fs.existsSync(path.join(dir, `${name}.json`))
    ? JSON.parse(fs.readFileSync(path.join(dir, `${name}.json`), 'utf8')) : {};
  const bytes = fs.statSync(file).size;
  totalBytes += bytes;
  totalTris += tris;
  assets.push({
    name, file: f, bytes, tris,
    trisSource: sidecar.tris_before ?? null,
    budget: sidecar.budget ?? null,
    textureBytes: textures.reduce((a, t) => a + t.bytes, 0),
    textures,
    materials,
    litScale: sidecar.lit_scale == null ? null : +(+sidecar.lit_scale).toPrecision(6),
    litAtlases: Object.fromEntries(Object.entries(sidecar.bake_stats ?? {}).filter(([k]) => k.startsWith('lit'))
      .map(([k, v]) => [k, { res: v.res, litScale: v.lit_scale, texelsPerMm: v.texels_per_mm, clipped: v.clipped_fraction }])),
    reduction: sidecar.reduction ?? null,
    nodes: root.listNodes().map((n) => n.getName()),
    anchors: sidecar.anchors ?? {},
    emissive,
    keepers: (sidecar.emissive_nodes ?? []).filter((e) => e.keeper),
    glass: Object.keys(sidecar.meshes ?? {}).filter((m) => m.includes('__glass_')),
    credits: (sidecar.credits ?? []).map((c) => c.key),
    sources: sidecar.sources ?? [],
  });
}

const manifest = {
  generated: new Date().toISOString(),
  generator: 'blender/scripts/v2_export_web.py -> scripts/optimize-glb.mjs -> scripts/props-manifest.mjs',
  source: 'blender/scene/room.blend (full scene; licensing gate lifted by the owner on 2026-10-01)',
  coordinates: 'world space: load each GLB at identity. glTF Y-up: three (x, y, z) = Blender (x, z, -y).',
  materials: 'Two baked atlases per asset. mode "lit": non-metal surfaces, KHR_materials_unlit, baseColor = the Cycles DIFFUSE bake (direct + indirect + colour) of the sunset room, stored as linear/litScale in sRGB: multiply the colour by material.userData.litScale (glTF extras) to restore it; no lights touch them. mode "pbr": metals (metallic >= 0.5), emissive parts, glass and keepers: baseColor + ORM (R=AO, G=roughness, B=metallic) (+ normal), lit at runtime by an environment capture of the baked room. Keepers (Robot_rsl_lens, bambu_mini_screen) are their own nodes and materials.',
  grade: 'Bakes are scene-linear like the room lightmaps: render with AgX, toneMappingExposure = 2 ** 0.45 (blender/bake/sunset/README.md).',
  totalBytes, totalTris,
  credits: CREDITS,
  assets,
};
fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(manifest, null, 1) + '\n');

const used = [...new Set(assets.flatMap((a) => a.credits))];
const credits = {
  note: 'CC BY 4.0 requires this credit to be visible wherever these models ship.',
  line: 'Models: ' + used.map((k) => `"${CREDITS[k].title}" by ${CREDITS[k].author}`).join(' · ') + ' — CC BY 4.0',
  items: used.map((k) => ({ key: k, ...CREDITS[k], assets: assets.filter((a) => a.credits.includes(k)).map((a) => a.file) })),
};
fs.writeFileSync(path.join(dir, 'CREDITS.json'), JSON.stringify(credits, null, 1) + '\n');

for (const a of assets) {
  console.log(`${a.file.padEnd(20)} ${String(a.tris).padStart(7)} tris ${(a.bytes / 1024).toFixed(0).padStart(6)} KB` +
    ` (tex ${(a.textureBytes / 1024).toFixed(0)} KB)  emissive ${a.emissive.length}  credits ${a.credits.join(',') || '-'}`);
}
console.log(`total ${assets.length} assets, ${totalTris} tris, ${(totalBytes / 1024 / 1024).toFixed(2)} MB`);
