import * as THREE from 'three';
import { FullScreenQuad, Pass } from 'three/addons/postprocessing/Pass.js';

/**
 * Bloom as a mip chain of separable Gaussian blurs, the same kernels and level weights as three's
 * UnrealBloomPass — without the three passes that pass spends around them.
 *
 * Stock: a luminosity high-pass into a half-resolution buffer, the blur chain, a half-resolution
 * composite of all five levels, then a full-resolution additive copy onto the image. Here the
 * threshold is applied to each tap of the first horizontal blur (the same per-pixel function,
 * evaluated where the blur reads), and the five blurred levels are left for the final composite
 * to sample directly. Two half-resolution passes and one full-resolution pass fewer per frame.
 */
const LEVELS = 5;
const KERNELS = [6, 10, 14, 18, 22];

function blurMaterial(kernelRadius: number, threshold: boolean) {
  const sigma = kernelRadius / 3;
  const coefficients: number[] = [];
  for (let i = 0; i < kernelRadius; i++) coefficients.push((0.39894 * Math.exp((-0.5 * i * i) / (sigma * sigma))) / sigma);
  // Adjacent taps merged into single bilinear fetches.
  const offsets: number[] = [];
  const weights: number[] = [];
  for (let i = 1; i < kernelRadius; i += 2) {
    const wa = coefficients[i];
    const wb = i + 1 < kernelRadius ? coefficients[i + 1] : 0;
    offsets.push((i * wa + (i + 1) * wb) / (wa + wb));
    weights.push(wa + wb);
  }
  return new THREE.ShaderMaterial({
    defines: { KERNEL_PAIRS: offsets.length, ...(threshold ? { THRESHOLD: '' } : {}) },
    uniforms: {
      colorTexture: { value: null },
      invSize: { value: new THREE.Vector2() },
      direction: { value: new THREE.Vector2() },
      centerWeight: { value: coefficients[0] },
      gaussianOffsets: { value: offsets },
      gaussianWeights: { value: weights },
      threshold: { value: 1 },
    },
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: /* glsl */ `
      #include <common>
      varying vec2 vUv;
      uniform sampler2D colorTexture;
      uniform vec2 invSize;
      uniform vec2 direction;
      uniform float centerWeight;
      uniform float gaussianOffsets[KERNEL_PAIRS];
      uniform float gaussianWeights[KERNEL_PAIRS];
      uniform float threshold;
      vec3 tap(vec2 uv) {
        vec3 c = texture2D(colorTexture, uv).rgb;
        #ifdef THRESHOLD
          // LuminosityHighPassShader's curve, smoothWidth 0.01.
          c *= smoothstep(threshold, threshold + 0.01, luminance(c));
        #endif
        return c;
      }
      void main() {
        vec3 sum = tap(vUv) * centerWeight;
        for (int i = 0; i < KERNEL_PAIRS; i++) {
          vec2 offset = direction * invSize * gaussianOffsets[i];
          sum += (tap(vUv + offset) + tap(vUv - offset)) * gaussianWeights[i];
        }
        gl_FragColor = vec4(sum, 1.0);
      }`,
    depthTest: false,
    depthWrite: false,
  });
}

export class BloomPass extends Pass {
  strength = 0.3;
  threshold = 1;
  /** Per-level weights, tightest first. */
  readonly levels = [1.2, 0.8, 0.25, 0.08, 0.05];
  private readonly getInput: () => THREE.Texture;
  private readonly horizontal: THREE.WebGLRenderTarget[] = [];
  private readonly vertical: THREE.WebGLRenderTarget[] = [];
  private readonly materials: THREE.ShaderMaterial[] = [];
  private readonly thresholdMaterial = blurMaterial(KERNELS[0], true);
  private readonly quad = new FullScreenQuad();

  constructor(getInput: () => THREE.Texture) {
    super();
    this.getInput = getInput;
    this.needsSwap = false;
    for (let i = 0; i < LEVELS; i++) {
      const options = { type: THREE.HalfFloatType, depthBuffer: false, generateMipmaps: false };
      this.horizontal.push(new THREE.WebGLRenderTarget(1, 1, options));
      this.vertical.push(new THREE.WebGLRenderTarget(1, 1, options));
      this.materials.push(blurMaterial(KERNELS[i], false));
    }
  }

  /** The blurred levels, half resolution first. */
  get textures() {
    return this.vertical.map((t) => t.texture);
  }

  /** Weight of each level as the composite applies it: UnrealBloomPass's strength × radius term × tint. */
  weight(level: number) {
    // lerpBloomFactor at radius 0.5 is 0.6 for every level.
    return this.strength * 0.6 * this.levels[level];
  }

  setSize(width: number, height: number) {
    let w = Math.round(width / 2);
    let h = Math.round(height / 2);
    for (let i = 0; i < LEVELS; i++) {
      this.horizontal[i].setSize(Math.max(1, w), Math.max(1, h));
      this.vertical[i].setSize(Math.max(1, w), Math.max(1, h));
      const inv = new THREE.Vector2(1 / Math.max(1, w), 1 / Math.max(1, h));
      this.materials[i].uniforms.invSize.value.copy(inv);
      if (i === 0) this.thresholdMaterial.uniforms.invSize.value.copy(inv);
      w = Math.round(w / 2);
      h = Math.round(h / 2);
    }
  }

  render(renderer: THREE.WebGLRenderer) {
    const autoClear = renderer.autoClear;
    renderer.autoClear = false;
    let input = this.getInput();
    for (let i = 0; i < LEVELS; i++) {
      const horizontal = i === 0 ? this.thresholdMaterial : this.materials[i];
      horizontal.uniforms.colorTexture.value = input;
      horizontal.uniforms.direction.value.set(1, 0);
      horizontal.uniforms.threshold.value = this.threshold;
      this.quad.material = horizontal;
      renderer.setRenderTarget(this.horizontal[i]);
      this.quad.render(renderer);

      const vertical = this.materials[i];
      vertical.uniforms.colorTexture.value = this.horizontal[i].texture;
      vertical.uniforms.direction.value.set(0, 1);
      this.quad.material = vertical;
      renderer.setRenderTarget(this.vertical[i]);
      this.quad.render(renderer);
      input = this.vertical[i].texture;
    }
    renderer.autoClear = autoClear;
  }

  dispose() {
    for (const t of [...this.horizontal, ...this.vertical]) t.dispose();
    for (const m of [...this.materials, this.thresholdMaterial]) m.dispose();
    this.quad.dispose();
  }
}
