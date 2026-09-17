import * as THREE from 'three';
import { Pass, FullScreenQuad } from 'three/addons/postprocessing/Pass.js';

/**
 * Light scattering in room air, for both the sun and the desk lamp.
 *
 * For each pixel, march from the camera to the visible surface and sample the real shadow
 * maps: light accumulates only where that light actually reaches, so daylight forms shafts
 * through the window occluded by the frame and the monitor, and the lamp's cone is genuinely
 * broken by its own shade, the medals hanging off the arm, and whatever is on the desk.
 *
 * Both lights share one march — same ray, two lookups — which is far cheaper than two passes.
 * Runs at reduced resolution with jittered samples and a separable blur, then adds into the
 * HDR image before bloom and tone mapping.
 *
 * This is raymarched scattering through shadow maps. It is not path tracing and not ray
 * tracing; it is the honest name for what it does.
 */
const STEPS = 28;
const BLACK = new THREE.Color(0, 0, 0);

const marchShader = {
  uniforms: {
    tDepth: { value: null as THREE.Texture | null },
    tShadow: { value: null as THREE.Texture | null },
    uShadowMatrix: { value: new THREE.Matrix4() },
    uProjInv: { value: new THREE.Matrix4() },
    uCamWorld: { value: new THREE.Matrix4() },
    uCamPos: { value: new THREE.Vector3() },
    uSunDir: { value: new THREE.Vector3() },
    uScatter: { value: new THREE.Color() },
    tSpotShadow: { value: null as THREE.Texture | null },
    uSpotMatrix: { value: new THREE.Matrix4() },
    uSpotPos: { value: new THREE.Vector3() },
    uSpotDir: { value: new THREE.Vector3(0, -1, 0) },
    uSpotScatter: { value: new THREE.Color() },
    /** cos(angle) and cos(angle * (1 - penumbra)): the cone edge and its soft shoulder. */
    uSpotCone: { value: new THREE.Vector2(0.8, 0.9) },
    uSpotRange: { value: 3 },
    uMaxDist: { value: 4 },
    uWindowZ: { value: -1.41 },
    uFrame: { value: 0 },
    // Strongly forward-scattering: that is what makes daylight read as beams near the
    // window rather than as an even haze filling the room.
    uAnisotropy: { value: 0.72 },
  },
  vertexShader: /* glsl */ `
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }
  `,
  fragmentShader: /* glsl */ `
    #define STEPS ${STEPS}
    uniform sampler2D tDepth;
    uniform sampler2DShadow tShadow;
    uniform sampler2DShadow tSpotShadow;
    uniform mat4 uShadowMatrix, uSpotMatrix, uProjInv, uCamWorld;
    uniform vec3 uCamPos, uSunDir, uScatter, uSpotPos, uSpotDir, uSpotScatter;
    uniform vec2 uSpotCone;
    uniform float uMaxDist, uWindowZ, uFrame, uAnisotropy, uSpotRange;
    varying vec2 vUv;

    float hg(float cosT, float g) {
      return (1.0 - g * g) / (12.566 * pow(max(1e-4, 1.0 + g * g - 2.0 * g * cosT), 1.5));
    }

    vec3 worldAt(vec2 uv, float depth) {
      vec4 view = uProjInv * vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
      view /= view.w;
      return (uCamWorld * view).xyz;
    }

    float ign(vec2 p) {
      return fract(52.9829189 * fract(dot(p, vec2(0.06711056, 0.00583715))));
    }

    void main() {
      vec3 end = worldAt(vUv, texture2D(tDepth, vUv).x);
      vec3 ray = end - uCamPos;
      float len = min(length(ray), uMaxDist);
      vec3 dir = normalize(ray);
      float stepLen = len / float(STEPS);
      float jitter = ign(gl_FragCoord.xy + uFrame * 5.588);

      float sunOn = step(1e-4, uScatter.r + uScatter.g + uScatter.b);
      float spotOn = step(1e-4, uSpotScatter.r + uSpotScatter.g + uSpotScatter.b);
      float g = uAnisotropy;

      float sunLit = 0.0;
      vec3 spotSum = vec3(0.0);
      for (int i = 0; i < STEPS; i++) {
        vec3 p = uCamPos + dir * ((float(i) + jitter) * stepLen);
        if (p.z < uWindowZ) break; // outdoors: not room air

        if (sunOn > 0.0) {
          vec4 sc = uShadowMatrix * vec4(p, 1.0);
          vec3 s = sc.xyz / sc.w;
          if (s.x > 0.0 && s.x < 1.0 && s.y > 0.0 && s.y < 1.0 && s.z < 1.0) {
            sunLit += texture(tShadow, s);
          }
        }

        if (spotOn > 0.0) {
          vec3 toLight = uSpotPos - p;
          float dist = length(toLight);
          vec3 L = toLight / max(dist, 1e-4);
          // Inside the cone, within range, and not shadowed by the shade or the medals.
          float cone = smoothstep(uSpotCone.x, uSpotCone.y, dot(-L, uSpotDir));
          if (cone > 0.0 && dist < uSpotRange) {
            vec4 lc = uSpotMatrix * vec4(p, 1.0);
            vec3 l = lc.xyz / lc.w;
            float vis = 1.0;
            if (l.x > 0.0 && l.x < 1.0 && l.y > 0.0 && l.y < 1.0 && l.z < 1.0) vis = texture(tSpotShadow, l);
            float fall = 1.0 / (1.0 + dist * dist * 2.2);
            float edge = 1.0 - smoothstep(uSpotRange * 0.55, uSpotRange, dist);
            // More forward-scattering than the sun term: a lamp beam is most visible looking into it.
            spotSum += vec3(vis * cone * fall * edge * hg(dot(dir, L), min(0.82, g + 0.12)));
          }
        }
      }

      vec3 sun = uScatter * sunLit * hg(dot(dir, uSunDir), g);
      gl_FragColor = vec4((sun + uSpotScatter * spotSum) * stepLen, 1.0);
    }
  `,
};

const blurShader = {
  uniforms: {
    tInput: { value: null as THREE.Texture | null },
    uDirection: { value: new THREE.Vector2() },
  },
  vertexShader: marchShader.vertexShader,
  fragmentShader: /* glsl */ `
    uniform sampler2D tInput;
    uniform vec2 uDirection;
    varying vec2 vUv;
    void main() {
      vec3 c = texture2D(tInput, vUv).rgb * 0.227;
      c += (texture2D(tInput, vUv + uDirection * 1.385).rgb + texture2D(tInput, vUv - uDirection * 1.385).rgb) * 0.316;
      c += (texture2D(tInput, vUv + uDirection * 3.231).rgb + texture2D(tInput, vUv - uDirection * 3.231).rgb) * 0.070;
      gl_FragColor = vec4(c, 1.0);
    }
  `,
};

export class VolumetricLightPass extends Pass {
  /** Sun scattering colour × strength. */
  readonly scatter = new THREE.Color(0, 0, 0);
  /** Lamp scattering colour × strength. Zero for both disables the pass entirely. */
  readonly lampScatter = new THREE.Color(0, 0, 0);
  private readonly camera: THREE.PerspectiveCamera;
  private readonly sun: THREE.DirectionalLight;
  private readonly lamp: THREE.SpotLight;
  private readonly getDepth: () => THREE.Texture | null;
  private readonly march = new THREE.ShaderMaterial(marchShader);
  private readonly blur = new THREE.ShaderMaterial(blurShader);
  private readonly quad = new FullScreenQuad();
  private readonly targetA = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, depthBuffer: false });
  private readonly targetB = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, depthBuffer: false });
  private frame = 0;
  /** True when the last render produced scattered light (`texture` holds it); false means add nothing. */
  active = false;
  /** Fraction of the drawing buffer the shafts render at. */
  resolutionScale: () => number = () => 0.4;

  constructor(
    camera: THREE.PerspectiveCamera,
    sun: THREE.DirectionalLight,
    lamp: THREE.SpotLight,
    getDepth: () => THREE.Texture | null,
  ) {
    super();
    this.camera = camera;
    this.sun = sun;
    this.lamp = lamp;
    this.getDepth = getDepth;
    for (const m of [this.march, this.blur]) {
      m.depthTest = false;
      m.depthWrite = false;
    }
    this.needsSwap = false;
  }

  setSize(width: number, height: number) {
    // Shafts are low-frequency and blurred: a fraction of the buffer is enough.
    const k = this.resolutionScale();
    const w = Math.max(1, Math.round(width * k));
    const h = Math.max(1, Math.round(height * k));
    this.targetA.setSize(w, h);
    this.targetB.setSize(w, h);
  }

  render(renderer: THREE.WebGLRenderer, _writeBuffer: THREE.WebGLRenderTarget, _readBuffer: THREE.WebGLRenderTarget) {
    const sunTex = this.sun.shadow.map?.depthTexture ?? null;
    const spotTex = this.lamp.shadow.map?.depthTexture ?? null;
    const depth = this.getDepth();
    const sunOn = this.scatter.r + this.scatter.g + this.scatter.b > 1e-4 && sunTex !== null;
    const spotOn = this.lampScatter.r + this.lampScatter.g + this.lampScatter.b > 1e-4 && spotTex !== null;
    const active = (sunOn || spotOn) && depth !== null;
    this.active = active;

    if (active) {
      this.frame++;
      const u = this.march.uniforms;
      u.tDepth.value = depth;
      // Both shadow samplers must stay bound to a real texture even when one light is off,
      // or the driver errors on an unbound sampler2DShadow. The scatter colour gates the term.
      u.tShadow.value = sunTex ?? spotTex;
      u.tSpotShadow.value = spotTex ?? sunTex;
      u.uShadowMatrix.value.copy(this.sun.shadow.matrix);
      u.uProjInv.value.copy(this.camera.projectionMatrixInverse);
      u.uCamWorld.value.copy(this.camera.matrixWorld);
      u.uCamPos.value.setFromMatrixPosition(this.camera.matrixWorld);
      u.uSunDir.value.subVectors(this.sun.position, this.sun.target.position).normalize();
      u.uScatter.value.copy(sunOn ? this.scatter : BLACK);
      u.uSpotScatter.value.copy(spotOn ? this.lampScatter : BLACK);

      if (spotOn) {
        this.lamp.updateWorldMatrix(true, false);
        u.uSpotMatrix.value.copy(this.lamp.shadow.matrix);
        u.uSpotPos.value.setFromMatrixPosition(this.lamp.matrixWorld);
        this.lamp.target.updateWorldMatrix(true, false);
        u.uSpotDir.value
          .setFromMatrixPosition(this.lamp.target.matrixWorld)
          .sub(u.uSpotPos.value)
          .normalize();
        const outer = Math.cos(this.lamp.angle);
        u.uSpotCone.value.set(outer, Math.cos(this.lamp.angle * (1 - this.lamp.penumbra * 0.9)));
        u.uSpotRange.value = this.lamp.distance > 0 ? this.lamp.distance : 3;
      }
      u.uFrame.value = this.frame % 64;

      this.quad.material = this.march;
      renderer.setRenderTarget(this.targetA);
      this.quad.render(renderer);

      this.quad.material = this.blur;
      this.blur.uniforms.tInput.value = this.targetA.texture;
      this.blur.uniforms.uDirection.value.set(1 / this.targetA.width, 0);
      renderer.setRenderTarget(this.targetB);
      this.quad.render(renderer);
      this.blur.uniforms.tInput.value = this.targetB.texture;
      this.blur.uniforms.uDirection.value.set(0, 1 / this.targetA.height);
      renderer.setRenderTarget(this.targetA);
      this.quad.render(renderer);
    }

    // The final composite adds `texture` in; nothing is drawn onto the image here.
  }

  /** Scattered light at reduced resolution, blurred. */
  get texture() {
    return this.targetA.texture;
  }

  dispose() {
    this.targetA.dispose();
    this.targetB.dispose();
    this.march.dispose();
    this.blur.dispose();
    this.quad.dispose();
  }
}
