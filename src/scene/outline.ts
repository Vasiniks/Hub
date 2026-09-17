import * as THREE from 'three';
import { OutlinePass } from 'three/addons/postprocessing/OutlinePass.js';

/**
 * The hover outline, without rendering the room again to find out what is in front of it.
 *
 * Stock OutlinePass draws every non-selected object into its own packed-depth target each
 * frame, purely so the edge can switch to the hidden colour where something occludes the
 * selection. Ambient occlusion has already rendered the scene's depth for the same camera in
 * the same frame, so this reads that instead: the whole room drops out of the hover cost and
 * only the selected object is drawn.
 *
 * The glow stage (a second, quarter-resolution blur chain) is also skipped while `edgeGlow`
 * is zero — its result is multiplied by zero in the overlay, so computing it was pure waste.
 */
interface Internals {
  _oldClearColor: THREE.Color;
  oldClearAlpha: number;
  _fsQuad: { material: THREE.Material; render(r: THREE.WebGLRenderer): void };
  _visibilityCache: Map<THREE.Object3D, boolean>;
  _selectionCache: Set<THREE.Object3D>;
  _updateSelectionCache(): void;
  _changeVisibilityOfNonSelectedObjects(v: boolean): void;
  _updateTextureMatrix(): void;
  textureMatrix: THREE.Matrix4;
  renderScene: THREE.Scene;
  renderCamera: THREE.PerspectiveCamera;
  prepareMaskMaterial: THREE.ShaderMaterial;
  renderTargetMaskBuffer: THREE.WebGLRenderTarget;
  renderTargetMaskDownSampleBuffer: THREE.WebGLRenderTarget;
  renderTargetEdgeBuffer1: THREE.WebGLRenderTarget;
  renderTargetEdgeBuffer2: THREE.WebGLRenderTarget;
  renderTargetBlurBuffer1: THREE.WebGLRenderTarget;
  renderTargetBlurBuffer2: THREE.WebGLRenderTarget;
  materialCopy: THREE.ShaderMaterial;
  copyUniforms: Record<string, THREE.IUniform>;
  edgeDetectionMaterial: THREE.ShaderMaterial;
  separableBlurMaterial1: THREE.ShaderMaterial;
  separableBlurMaterial2: THREE.ShaderMaterial;
  overlayMaterial: THREE.ShaderMaterial;
  patternTexture: THREE.Texture;
  tempPulseColor1: THREE.Color;
  tempPulseColor2: THREE.Color;
}

const Blur = OutlinePass as unknown as { BlurDirectionX: THREE.Vector2; BlurDirectionY: THREE.Vector2 };

export class SharedDepthOutlinePass extends OutlinePass {
  /** Full-resolution selection mask (r: selected, g: visible), for the final composite. */
  get maskTexture() {
    return (this as unknown as Internals).renderTargetMaskBuffer.texture;
  }

  /** Blurred edge, half resolution. */
  get edgeTexture() {
    return (this as unknown as Internals).renderTargetEdgeBuffer1.texture;
  }

  private readonly getDepth: () => THREE.Texture | null;

  constructor(
    resolution: THREE.Vector2,
    scene: THREE.Scene,
    camera: THREE.PerspectiveCamera,
    getDepth: () => THREE.Texture | null,
  ) {
    super(resolution, scene, camera);
    this.getDepth = getDepth;
    const mask = (this as unknown as Internals).prepareMaskMaterial;
    // A real depth texture holds window depth in .x; no RGBA unpacking. The bias keeps the
    // selection from occluding itself against depth sampled at a coarser resolution.
    mask.fragmentShader = mask.fragmentShader
      .replace('unpackRGBAToDepth(texture2DProj( depthTexture, projTexCoord ))', 'texture2DProj( depthTexture, projTexCoord ).x')
      .replace('(-vPosition.z > viewZ)', '(-vPosition.z > viewZ + 0.012)');
    mask.needsUpdate = true;
  }

  render(
    renderer: THREE.WebGLRenderer,
    _writeBuffer: THREE.WebGLRenderTarget,
    readBuffer: THREE.WebGLRenderTarget,
    _deltaTime?: number,
    maskActive?: boolean,
  ) {
    const self = this as unknown as Internals & OutlinePass;
    const depth = this.getDepth();
    // No shared depth this frame (AO switched off for profiling): fall back to the stock path.
    if (!depth) return super.render(renderer, _writeBuffer, readBuffer, _deltaTime ?? 0, maskActive ?? false);
    if (this.selectedObjects.length > 0) {
      renderer.getClearColor(self._oldClearColor);
      self.oldClearAlpha = renderer.getClearAlpha();
      const oldAutoClear = renderer.autoClear;
      renderer.autoClear = false;
      if (maskActive) renderer.state.buffers.stencil.setTest(false);
      renderer.setClearColor(0xffffff, 1);

      self._updateSelectionCache();
      const scene = self.renderScene;
      const background = scene.background;
      const override = scene.overrideMaterial;
      scene.background = null;

      // Only the selected objects, depth-tested against the scene depth AO already rendered.
      self._updateTextureMatrix();
      self._changeVisibilityOfNonSelectedObjects(false);
      scene.overrideMaterial = self.prepareMaskMaterial;
      const u = self.prepareMaskMaterial.uniforms;
      u.cameraNearFar.value.set(self.renderCamera.near, self.renderCamera.far);
      u.depthTexture.value = depth;
      u.textureMatrix.value = self.textureMatrix;
      renderer.setRenderTarget(self.renderTargetMaskBuffer);
      renderer.clear();
      renderer.render(scene, self.renderCamera);
      self._changeVisibilityOfNonSelectedObjects(true);
      self._visibilityCache.clear();
      self._selectionCache.clear();
      scene.background = background;
      scene.overrideMaterial = override;

      // Downsample, edge-detect, and blur for edge thickness — as stock.
      const quad = self._fsQuad;
      quad.material = self.materialCopy;
      self.copyUniforms.tDiffuse.value = self.renderTargetMaskBuffer.texture;
      renderer.setRenderTarget(self.renderTargetMaskDownSampleBuffer);
      renderer.clear();
      quad.render(renderer);

      self.tempPulseColor1.copy(this.visibleEdgeColor);
      self.tempPulseColor2.copy(this.hiddenEdgeColor);

      quad.material = self.edgeDetectionMaterial;
      const e = self.edgeDetectionMaterial.uniforms;
      e.maskTexture.value = self.renderTargetMaskDownSampleBuffer.texture;
      e.texSize.value.set(self.renderTargetMaskDownSampleBuffer.width, self.renderTargetMaskDownSampleBuffer.height);
      e.visibleEdgeColor.value = self.tempPulseColor1;
      e.hiddenEdgeColor.value = self.tempPulseColor2;
      renderer.setRenderTarget(self.renderTargetEdgeBuffer1);
      renderer.clear();
      quad.render(renderer);

      quad.material = self.separableBlurMaterial1;
      const b1 = self.separableBlurMaterial1.uniforms;
      b1.colorTexture.value = self.renderTargetEdgeBuffer1.texture;
      b1.direction.value = Blur.BlurDirectionX;
      b1.kernelRadius.value = this.edgeThickness;
      renderer.setRenderTarget(self.renderTargetBlurBuffer1);
      renderer.clear();
      quad.render(renderer);
      b1.colorTexture.value = self.renderTargetBlurBuffer1.texture;
      b1.direction.value = Blur.BlurDirectionY;
      renderer.setRenderTarget(self.renderTargetEdgeBuffer1);
      renderer.clear();
      quad.render(renderer);

      if (this.edgeGlow > 0) {
        quad.material = self.separableBlurMaterial2;
        const b2 = self.separableBlurMaterial2.uniforms;
        b2.colorTexture.value = self.renderTargetEdgeBuffer1.texture;
        b2.direction.value = Blur.BlurDirectionX;
        renderer.setRenderTarget(self.renderTargetBlurBuffer2);
        renderer.clear();
        quad.render(renderer);
        b2.colorTexture.value = self.renderTargetBlurBuffer2.texture;
        b2.direction.value = Blur.BlurDirectionY;
        renderer.setRenderTarget(self.renderTargetEdgeBuffer2);
        renderer.clear();
        quad.render(renderer);
      }

      // The overlay itself (edge colour over the image) is drawn by the final composite, from
      // `maskTexture` and `edgeTexture`: no full-resolution buffer is written here.
      renderer.setClearColor(self._oldClearColor, self.oldClearAlpha);
      renderer.autoClear = oldAutoClear;
    }

  }
}
