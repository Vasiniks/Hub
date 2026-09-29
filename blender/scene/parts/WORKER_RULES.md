# Rules for Blender asset workers

- Repo: C:\Users\Vas\Documents\Github\Hub. Blender: "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" (5.2.2 LTS).
  Headless build: `"<exe>" -b --factory-startup --python <script> -- <args>`. Measure: `"<exe>" -b blender/scene/room.blend --python <script>`.
- Room scene: blender/scene/room.blend — Z-up, metres, desk top z=0.735, seated viewer at (0,-0.16,1.175) looking +Y (toward monitor/window).
  NEVER save or modify room.blend (open it headless read-only; you may append objects from it into your own file for context renders, but keep them out of your output collection).
  Do NOT use any mcp__blender__* tools — the live Blender belongs to the orchestrator. Don't touch src/, don't commit.
- Re-runnable build script: blender/scripts/v2_<name>.py. Output: blender/scene/parts/<name>.blend with ONE collection `NEW_<name>` under ONE root empty `NEW_<name>_root`, plus previews blender/scene/parts/<name>_*.png.
- Quality bar: reads as the real product at close range — real dimensions, bevelled/rounded edges, seams and gaps, subdivision where needed, nothing primitive-looking. Read your previews (Read tool) and iterate.
- Materials: node-based Principled BSDF, procedural with micro roughness variation and fine bump where real. No downloaded models or anything needing an account. If you truly need a scanned texture: CC0 only from ambientCG or Poly Haven public URLs, ≤2K, stored under assets/textures/<name>/, with a row in assets/MANIFEST.md. Look up shader nodes by type, not name.
- Previews: Cycles GPU — `prefs=bpy.context.preferences.addons['cycles'].preferences; prefs.compute_device_type='OPTIX'; prefs.refresh_devices(); [setattr(d,'use',d.type=='OPTIX') for d in prefs.devices]; scene.cycles.device='GPU'`, 64 spp, OptiX denoise, ~1280x800, simple 3-point light + neutral grey world. Other workers share the GPU — keep each render under ~60 s.
- If you use WebSearch/WebFetch for reference, don't invent features you couldn't verify; say what you assumed.
- Never overstate what you did. Final report ≤150 words: files, collection/root, placement, tri count, exact names of old objects in room.blend replaced, shortcomings.
