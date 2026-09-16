import * as THREE from 'three';
import { Pass, FullScreenQuad } from 'three/addons/postprocessing/Pass.js';

/**
 * Sunlight scattering in room air. For each pixel, march from the camera to the
 * visible surface and sample the real sun shadow map: light accumulates only where
 * the sun actually reaches, so shafts form through the window and are occluded by
 * the frame, monitor, and lamp. Runs at reduced resolution with jittered samples
 * and a separable blur, then adds into the HDR image before bloom and tone mapping.
 */
const STEPS = 28;

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
    uMaxDist: { value: 4 },
    uWindowZ: { value: -1.12 },
    uFrame: { value: 0 },
    uAnisotropy: { value: 0.55 },
  },
  vertexShader: /* glsl */ `
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }
  `,
  fragmentShader: /* glsl */ `
    #define STEPS ${STEPS}
    uniform sampler2D tDepth;
    uniform sampler2DShadow tShadow;
    uniform mat4 uShadowMatrix, uProjInv, uCamWorld;
    uniform vec3 uCamPos, uSunDir, uScatter;
    uniform float uMaxDist, uWindowZ, uFrame, uAnisotropy;
    varying vec2 vUv;

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

      float lit = 0.0;
      for (int i = 0; i < STEPS; i++) {
        vec3 p = uCamPos + dir * ((float(i) + jitter) * stepLen);
        if (p.z < uWindowZ) break; // outdoors: not room air
        vec4 sc = uShadowMatrix * vec4(p, 1.0);
        vec3 s = sc.xyz / sc.w;
        if (s.x > 0.0 && s.x < 1.0 && s.y > 0.0 && s.y < 1.0 && s.z < 1.0) {
          lit += texture(tShadow, s);
        }
      }

      float g = uAnisotropy;
      float cosT = dot(dir, uSunDir);
      float phase = (1.0 - g * g) / (12.566 * pow(1.0 + g * g - 2.0 * g * cosT, 1.5));
      gl_FragColor = vec4(uScatter * lit * stepLen * phase, 1.0);
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

const compositeShader = {
  uniforms: {
    tDiffuse: { value: null as THREE.Texture | null },
    tScatter: { value: null as THREE.Texture | null },
  },
  vertexShader: marchShader.vertexShader,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse, tScatter;
    varying vec2 vUv;
    void main() {
      vec4 base = texture2D(tDiffuse, vUv);
      gl_FragColor = vec4(base.rgb + texture2D(tScatter, vUv).rgb, base.a);
    }
  `,
};

export class VolumetricLightPass extends Pass {
  /** Scattering colour × strength; zero disables the pass entirely. */
  readonly scatter = new THREE.Color(0, 0, 0);
  private readonly camera: THREE.PerspectiveCamera;
  private readonly sun: THREE.DirectionalLight;
  private readonly getDepth: () => THREE.Texture | null;
  private readonly march = new THREE.ShaderMaterial(marchShader);
  private readonly blur = new THREE.ShaderMaterial(blurShader);
  private readonly composite = new THREE.ShaderMaterial(compositeShader);
  private readonly quad = new FullScreenQuad();
  private readonly targetA = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, depthBuffer: false });
  private readonly targetB = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, depthBuffer: false });
  private frame = 0;
  /** Fraction of the drawing buffer the shafts render at. */
  resolutionScale: () => number = () => 0.4;

  constructor(camera: THREE.PerspectiveCamera, sun: THREE.DirectionalLight, getDepth: () => THREE.Texture | null) {
    super();
    this.camera = camera;
    this.sun = sun;
    this.getDepth = getDepth;
    for (const m of [this.march, this.blur, this.composite]) {
      m.depthTest = false;
      m.depthWrite = false;
    }
  }

  setSize(width: number, height: number) {
    // Shafts are low-frequency and blurred: a fraction of the buffer is enough.
    const k = this.resolutionScale();
    const w = Math.max(1, Math.round(width * k));
    const h = Math.max(1, Math.round(height * k));
    this.targetA.setSize(w, h);
    this.targetB.setSize(w, h);
  }

  render(renderer: THREE.WebGLRenderer, writeBuffer: THREE.WebGLRenderTarget, readBuffer: THREE.WebGLRenderTarget) {
    const shadowTex = this.sun.shadow.map?.depthTexture ?? null;
    const depth = this.getDepth();
    const active = this.scatter.r + this.scatter.g + this.scatter.b > 1e-4 && shadowTex !== null && depth !== null;

    if (active) {
      this.frame++;
      const u = this.march.uniforms;
      u.tDepth.value = depth;
      u.tShadow.value = shadowTex;
      u.uShadowMatrix.value.copy(this.sun.shadow.matrix);
      u.uProjInv.value.copy(this.camera.projectionMatrixInverse);
      u.uCamWorld.value.copy(this.camera.matrixWorld);
      u.uCamPos.value.setFromMatrixPosition(this.camera.matrixWorld);
      u.uSunDir.value.subVectors(this.sun.position, this.sun.target.position).normalize();
      u.uScatter.value.copy(this.scatter);
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

    if (!active) {
      // Nothing to add (night, or no shadow map yet): leave the image untouched and skip the swap.
      this.needsSwap = false;
      return;
    }
    this.needsSwap = true;
    this.quad.material = this.composite;
    this.composite.uniforms.tDiffuse.value = readBuffer.texture;
    this.composite.uniforms.tScatter.value = this.targetA.texture;
    renderer.setRenderTarget(this.renderToScreen ? null : writeBuffer);
    this.quad.render(renderer);
  }

  dispose() {
    this.targetA.dispose();
    this.targetB.dispose();
    this.march.dispose();
    this.blur.dispose();
    this.composite.dispose();
    this.quad.dispose();
  }
}
