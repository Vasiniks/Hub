import * as THREE from 'three';
import type { RoomRefs } from '../scene/room';
import { CAMERA } from '../scene/layout';

export type RigMode = 'standing' | 'sitting' | 'seated' | 'focusing' | 'focused' | 'returning';

export interface FocusTarget {
  center: THREE.Vector3;
  distance: number;
  yaw: number;
  pitch: number;
  /**
   * How far to aim right of the object, as a fraction of `distance`, so it sits left of centre
   * beside the panel. The bookshelf wants a near-centred frame, so it passes a small value.
   */
  offset?: number;
}

const UP = new THREE.Vector3(0, 1, 0);
// Scratch objects: per-frame camera work allocates nothing.
const _euler = new THREE.Euler(0, 0, 0, 'YXZ');
const _q = new THREE.Quaternion();
const _v1 = new THREE.Vector3();
const _v2 = new THREE.Vector3();
const SIT_STEP = new THREE.Vector3(-0.42, -0.03, -0.26);
const SIT_LOWER = new THREE.Vector3(0.06, 0.16, 0.2);

/** Calm centre, deliberate edges: the middle of the screen is for pointing, the edges are for turning. */
function shapeAxis(v: number, deadZone: number) {
  const a = THREE.MathUtils.clamp((Math.abs(v) - deadZone) / (1 - deadZone), 0, 1);
  return Math.sign(v) * a * a * (3 - 2 * a);
}

/** Quintic ease: no velocity or acceleration discontinuity at either end. */
const smoother = (t: number) => t * t * t * (t * (t * 6 - 15) + 10);
const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

function bezier(out: THREE.Vector3, p0: THREE.Vector3, p1: THREE.Vector3, p2: THREE.Vector3, p3: THREE.Vector3, t: number) {
  const u = 1 - t;
  return out
    .copy(p0).multiplyScalar(u * u * u)
    .addScaledVector(p1, 3 * u * u * t)
    .addScaledVector(p2, 3 * u * t * t)
    .addScaledVector(p3, t * t * t);
}

function yawPitchTo(from: THREE.Vector3, to: THREE.Vector3) {
  const d = to.clone().sub(from);
  return { yaw: Math.atan2(-d.x, -d.z), pitch: Math.atan2(d.y, Math.hypot(d.x, d.z)) };
}

function lookQuaternion(eye: THREE.Vector3, target: THREE.Vector3) {
  return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().lookAt(eye, target, UP));
}

export class CameraRig {
  mode: RigMode = 'standing';
  onSeated?: () => void;
  onFocusProgress?: (t: number) => void;
  onReturned?: () => void;

  private readonly camera: THREE.PerspectiveCamera;
  private readonly room: RoomRefs;
  private readonly reduced: boolean;

  private readonly standPos = new THREE.Vector3(...CAMERA.stand.position);
  private readonly standLook = yawPitchTo(this.standPos, new THREE.Vector3(...CAMERA.stand.lookAt));
  private readonly seatPos = new THREE.Vector3(...CAMERA.seat.position);
  private readonly seatLook = yawPitchTo(this.seatPos, new THREE.Vector3(...CAMERA.seat.lookAt));

  private pointer = new THREE.Vector2();
  private lookYaw = 0;
  private lookPitch = 0;
  private lookBlend = 1;
  private holding = false;
  private lookVelYaw = 0;
  private lookVelPitch = 0;
  private targetYaw = 0;
  private targetPitch = 0;
  private savedLook = { yaw: 0, pitch: 0 };

  /** Lens: the focus move dollies in a little, which reads as a camera rather than a teleport. */
  private fov = CAMERA.fov;
  private fovFrom = CAMERA.fov;
  private fovTo = CAMERA.fov;

  private t0 = 0;
  private duration = 1;
  private clock = 0;
  private fromPos = new THREE.Vector3();
  private fromQuat = new THREE.Quaternion();
  private toPos = new THREE.Vector3();
  private toQuat = new THREE.Quaternion();
  private arcA = new THREE.Vector3();
  private arcB = new THREE.Vector3();

  constructor(camera: THREE.PerspectiveCamera, room: RoomRefs, reducedMotion: boolean) {
    this.camera = camera;
    this.room = room;
    this.reduced = reducedMotion;
    this.camera.position.copy(this.standPos);
    this.camera.quaternion.copy(this.baseQuat(this.standLook, 0, 0));
  }

  get interactive() {
    return this.mode === 'seated' || this.mode === 'standing';
  }

  setPointer(nx: number, ny: number) {
    this.pointer.set(nx, ny);
  }

  /**
   * How hard the head is turned toward its limit, 0 at rest and 1 at the edge.
   *
   * Picking uses this: in the middle of the screen the cursor is pointing at things, but once
   * the visitor has pushed the view all the way over, they are turning to look at something —
   * and whatever they are reaching for is in the centre of the frame, not under the cursor.
   */
  lookExtent() {
    const standing = this.mode === 'standing';
    const yawRange = standing ? CAMERA.standYaw : CAMERA.seatYaw;
    const pitchRange = standing ? CAMERA.standPitch : CAMERA.seatPitch;
    const yaw = Math.abs(this.lookYaw) / (this.lookYaw >= 0 ? yawRange[0] : yawRange[1]);
    const pitch = Math.abs(this.lookPitch) / (this.lookPitch >= 0 ? pitchRange[1] : pitchRange[0]);
    return Math.max(yaw, pitch);
  }

  sitDown() {
    if (this.mode !== 'standing') return false;
    this.begin('sitting', this.reduced ? 0.9 : 2.9);
    this.fromPos.copy(this.camera.position);
    this.fromQuat.copy(this.camera.quaternion);
    return true;
  }

  focus(target: FocusTarget) {
    if (this.mode !== 'seated' && this.mode !== 'returning' && this.mode !== 'focused') return;
    if (this.mode === 'seated') this.savedLook = { yaw: this.lookYaw, pitch: this.lookPitch };
    this.begin('focusing', this.reduced ? 0.35 : 1.5);
    this.fovFrom = this.fov;
    this.fovTo = CAMERA.focusFov;
    this.fromPos.copy(this.camera.position);
    this.fromQuat.copy(this.camera.quaternion);

    const { center, distance, yaw, pitch } = target;
    this.toPos.set(
      center.x + Math.sin(yaw) * Math.cos(pitch) * distance,
      center.y + Math.sin(pitch) * distance,
      center.z + Math.cos(yaw) * Math.cos(pitch) * distance,
    );
    // Aim slightly to the right of the object so it sits left of centre, beside the panel.
    const forward = center.clone().sub(this.toPos).normalize();
    const right = new THREE.Vector3().crossVectors(forward, UP).normalize();
    const aim = center.clone().addScaledVector(right, distance * (target.offset ?? 0.3));
    this.toQuat.copy(lookQuaternion(this.toPos, aim));

    const lift = Math.min(0.12, distance * 0.08);
    this.arcA.copy(this.fromPos).lerp(this.toPos, 0.3).addScaledVector(UP, lift);
    this.arcB.copy(this.fromPos).lerp(this.toPos, 0.75).addScaledVector(UP, lift * 0.5);
  }

  unfocus() {
    if (this.mode !== 'focused' && this.mode !== 'focusing') return false;
    this.begin('returning', this.reduced ? 0.3 : 1.2);
    this.fovFrom = this.fov;
    this.fovTo = CAMERA.fov;
    this.fromPos.copy(this.camera.position);
    this.fromQuat.copy(this.camera.quaternion);
    this.lookYaw = this.targetYaw = this.savedLook.yaw;
    this.lookPitch = this.targetPitch = this.savedLook.pitch;
    this.lookVelYaw = this.lookVelPitch = 0;
    this.toPos.copy(this.seatPos);
    this.toQuat.copy(this.baseQuat(this.seatLook, this.lookYaw, this.lookPitch));
    this.arcA.copy(this.fromPos).lerp(this.toPos, 0.35).addScaledVector(UP, 0.03);
    this.arcB.copy(this.fromPos).lerp(this.toPos, 0.8);
    return true;
  }

  private begin(mode: RigMode, duration: number) {
    this.mode = mode;
    this.t0 = this.clock;
    this.duration = duration;
  }

  private baseQuat(base: { yaw: number; pitch: number }, yaw: number, pitch: number, roll = 0) {
    return _q.setFromEuler(_euler.set(base.pitch + pitch, base.yaw + yaw, roll, 'YXZ'));
  }

  /** While the cursor rests on an object the head stays put, so the object doesn't slide away. */
  holdLook(hold: boolean) {
    this.holding = hold;
  }

  private updateLook(dt: number, yawRange: [number, number], pitchRange: [number, number]) {
    if (this.holding) {
      this.targetYaw = this.lookYaw;
      this.targetPitch = this.lookPitch;
    } else {
      const sx = shapeAxis(this.pointer.x, CAMERA.deadZoneX);
      const sy = shapeAxis(this.pointer.y, CAMERA.deadZoneY);
      this.targetYaw = sx > 0 ? -sx * yawRange[1] : -sx * yawRange[0];
      this.targetPitch = sy > 0 ? sy * pitchRange[1] : sy * pitchRange[0];
    }
    // Critically damped spring: the head gathers speed rather than jumping, so a cursor that lands on
    // an object registers before the view turns away from it.
    const stiffness = 4.2 * 4.2;
    const damping = 2 * 4.2;
    if (this.holding) {
      const decay = Math.exp(-14 * dt);
      this.lookVelYaw *= decay;
      this.lookVelPitch *= decay;
    }
    this.lookVelYaw += (stiffness * (this.targetYaw - this.lookYaw) - damping * this.lookVelYaw) * dt;
    this.lookYaw += this.lookVelYaw * dt;
    this.lookVelPitch += (stiffness * (this.targetPitch - this.lookPitch) - damping * this.lookVelPitch) * dt;
    this.lookPitch += this.lookVelPitch * dt;
  }

  private readonly idleOut = { y: 0, yaw: 0, pitch: 0 };
  private idle(time: number) {
    const o = this.idleOut;
    if (this.reduced) {
      o.y = o.yaw = o.pitch = 0;
      return o;
    }
    o.y = Math.sin(time * 1.32) * 0.0022 + Math.sin(time * 0.37 + 1.3) * 0.0014;
    o.yaw = Math.sin(time * 0.23 + 0.7) * 0.0035 + Math.sin(time * 0.071) * 0.005;
    o.pitch = Math.sin(time * 0.17 + 2.1) * 0.0028 + Math.sin(time * 0.53) * 0.0009;
    return o;
  }

  /** Only touches the projection matrix when the value actually moves. */
  private setFov(next: number) {
    if (Math.abs(next - this.fov) < 0.01) return;
    this.fov = next;
    this.camera.fov = next;
    this.camera.updateProjectionMatrix();
  }

  update(dt: number) {
    this.clock += dt;
    const time = this.clock;
    const idle = this.idle(time);
    const u = Math.min(1, (time - this.t0) / this.duration);

    switch (this.mode) {
      case 'standing': {
        this.updateLook(dt, CAMERA.standYaw, CAMERA.standPitch);
        this.camera.position.copy(this.standPos).y += idle.y * 1.4;
        this.camera.quaternion.copy(this.baseQuat(this.standLook, this.lookYaw + idle.yaw * 1.3, this.lookPitch + idle.pitch));
        break;
      }
      case 'sitting': {
        const e = smoother(u);
        // Step toward the chair, turn into it, lower, and settle into the cushion.
        const p1 = _v1.copy(this.fromPos).add(SIT_STEP);
        const p2 = _v2.copy(this.seatPos).add(SIT_LOWER);
        bezier(this.camera.position, this.fromPos, p1, p2, this.seatPos, e);
        if (u > 0.78) this.camera.position.y -= Math.sin(Math.PI * ((u - 0.78) / 0.22)) * 0.022;

        const lookAway = Math.pow(Math.sin(Math.PI * e), 1.5);
        const yaw = THREE.MathUtils.lerp(this.standLook.yaw + this.lookYaw, this.seatLook.yaw, e);
        const pitch = THREE.MathUtils.lerp(this.standLook.pitch + this.lookPitch, this.seatLook.pitch, e) - lookAway * 0.2;
        const roll = Math.sin(Math.PI * e) * 0.028;
        this.camera.quaternion.setFromEuler(_euler.set(pitch, yaw, roll, 'YXZ'));

        const c = easeOutCubic(THREE.MathUtils.clamp((u - 0.12) / 0.62, 0, 1));
        this.room.chair.position.lerpVectors(this.room.chairStart.position, this.room.chairSeated.position, c);
        this.room.chair.rotation.y = THREE.MathUtils.lerp(this.room.chairStart.rotationY, this.room.chairSeated.rotationY, c);

        if (u >= 1) {
          this.mode = 'seated';
          this.lookYaw = this.targetYaw = 0;
          this.lookPitch = this.targetPitch = 0;
          this.lookVelYaw = this.lookVelPitch = 0;
          this.lookBlend = 0;
          this.onSeated?.();
        }
        break;
      }
      case 'seated': {
        this.lookBlend = Math.min(1, this.lookBlend + dt / 1.2);
        this.updateLook(dt * this.lookBlend, CAMERA.seatYaw, CAMERA.seatPitch);
        this.camera.position.copy(this.seatPos).y += idle.y;
        this.camera.quaternion.copy(this.baseQuat(this.seatLook, this.lookYaw + idle.yaw, this.lookPitch + idle.pitch));
        break;
      }
      case 'focusing':
      case 'returning': {
        const e = smoother(u);
        bezier(this.camera.position, this.fromPos, this.arcA, this.arcB, this.toPos, e);
        this.camera.quaternion.slerpQuaternions(this.fromQuat, this.toQuat, e);
        this.setFov(THREE.MathUtils.lerp(this.fovFrom, this.fovTo, e));
        if (this.mode === 'focusing') this.onFocusProgress?.(u);
        if (u >= 1) {
          if (this.mode === 'focusing') this.mode = 'focused';
          else {
            this.mode = 'seated';
            this.lookBlend = 0.35;
            this.onReturned?.();
          }
        }
        break;
      }
      case 'focused': {
        // Tiny parallax so the examined object never freezes.
        const px = this.reduced ? 0 : this.pointer.x * 0.02;
        const py = this.reduced ? 0 : this.pointer.y * 0.012;
        this.camera.position.copy(this.toPos).y += idle.y * 0.6;
        this.camera.quaternion.copy(this.toQuat).multiply(_q.setFromEuler(_euler.set(py + idle.pitch * 0.6, -px + idle.yaw * 0.6, 0, 'YXZ')));
        break;
      }
    }
  }
}
