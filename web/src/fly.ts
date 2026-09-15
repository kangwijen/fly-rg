import * as THREE from "three";
import type { Pose } from "./protocol";

const FEMUR_LEN = 0.22;
const TIBIA_LEN = 0.16;
const REAR_LEN = 0.16;
const MAX_REACH = 0.55;
const HOVER_AIR = 0.055;
const HOVER_TAP = 0;
const TIP_FOLLOW = 24;
const ELBOW_MIN = 0.045;
const Y_AXIS = new THREE.Vector3(0, 1, 0);

type ForeLimb = {
  femur: THREE.Mesh;
  tibia: THREE.Mesh;
  hand: THREE.Mesh;
};

/**
 * Drosophila-style fruit fly. Forelegs hover just off the glass and
 * plant on the pad when striking.
 */
export class FruitFly {
  readonly group = new THREE.Group();
  private body: THREE.Group;
  private head: THREE.Mesh;
  private leftWing: THREE.Mesh;
  private rightWing: THREE.Mesh;
  private midHind: THREE.Mesh[] = [];
  private leftArm: ForeLimb;
  private rightArm: ForeLimb;
  private leftHip = new THREE.Vector3(-0.045, 0.04, 0.055);
  private rightHip = new THREE.Vector3(0.045, 0.04, 0.055);
  private leftTip = new THREE.Vector3();
  private rightTip = new THREE.Vector3();
  private tipInitialized = false;
  private screenNormal = new THREE.Vector3(0, 0, 1);
  private readonly _dir = new THREE.Vector3();
  private readonly _mid = new THREE.Vector3();
  private readonly _from = new THREE.Vector3();
  private readonly _to = new THREE.Vector3();
  private readonly _elbow = new THREE.Vector3();
  private readonly _pole = new THREE.Vector3();
  private readonly _ortho = new THREE.Vector3();
  private readonly _leftTarget = new THREE.Vector3();
  private readonly _rightTarget = new THREE.Vector3();
  private readonly _hipWorld = new THREE.Vector3();
  private lastElapsed = 0;
  private baseY = 0;

  constructor() {
    const bodyMat = new THREE.MeshStandardMaterial({
      color: 0x3a2a18,
      roughness: 0.7,
      metalness: 0.04,
    });
    const stripeMat = new THREE.MeshStandardMaterial({
      color: 0x1c140c,
      roughness: 0.65,
    });
    const thoraxMat = new THREE.MeshStandardMaterial({
      color: 0x4a3824,
      roughness: 0.55,
      metalness: 0.06,
    });
    const wingMat = new THREE.MeshStandardMaterial({
      color: 0xc5e4f0,
      transparent: true,
      opacity: 0.38,
      roughness: 0.2,
      metalness: 0.05,
      side: THREE.DoubleSide,
    });
    const eyeMat = new THREE.MeshStandardMaterial({
      color: 0xc02820,
      emissive: 0x501010,
      emissiveIntensity: 0.45,
      roughness: 0.3,
    });
    const legMat = new THREE.MeshStandardMaterial({
      color: 0x1a1410,
      roughness: 0.75,
    });
    const headMat = new THREE.MeshStandardMaterial({
      color: 0x2e2418,
      roughness: 0.55,
    });

    this.body = new THREE.Group();
    this.group.add(this.body);

    const abdomen = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.055, 0.16, 6, 12),
      bodyMat,
    );
    abdomen.rotation.x = Math.PI / 2;
    abdomen.position.set(0, 0.07, -0.1);
    this.body.add(abdomen);

    for (let i = 0; i < 4; i++) {
      const band = new THREE.Mesh(
        new THREE.TorusGeometry(0.056, 0.006, 6, 16),
        stripeMat,
      );
      band.position.set(0, 0.07, -0.04 - i * 0.035);
      this.body.add(band);
    }

    const thorax = new THREE.Mesh(
      new THREE.SphereGeometry(0.07, 14, 12),
      thoraxMat,
    );
    thorax.scale.set(1.05, 0.85, 1.15);
    thorax.position.set(0, 0.085, 0.04);
    this.body.add(thorax);

    this.head = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 10), headMat);
    this.head.position.set(0, 0.08, 0.125);
    this.body.add(this.head);

    const leftEye = new THREE.Mesh(new THREE.SphereGeometry(0.032, 10, 8), eyeMat);
    leftEye.scale.set(0.85, 1.05, 0.9);
    leftEye.position.set(-0.038, 0.008, 0.018);
    this.head.add(leftEye);
    const rightEye = leftEye.clone();
    rightEye.position.x = 0.038;
    this.head.add(rightEye);

    const antGeo = new THREE.CylinderGeometry(0.003, 0.002, 0.045, 5);
    const antL = new THREE.Mesh(antGeo, legMat);
    antL.position.set(-0.02, 0.04, 0.03);
    antL.rotation.z = 0.45;
    antL.rotation.x = -0.6;
    this.head.add(antL);
    const antR = antL.clone();
    antR.position.x = 0.02;
    antR.rotation.z = -0.45;
    this.head.add(antR);

    this.leftWing = new THREE.Mesh(new THREE.PlaneGeometry(0.22, 0.09), wingMat);
    this.leftWing.position.set(-0.08, 0.12, 0.0);
    this.leftWing.rotation.set(-0.35, 0.15, 0.55);
    this.body.add(this.leftWing);

    this.rightWing = new THREE.Mesh(new THREE.PlaneGeometry(0.22, 0.09), wingMat);
    this.rightWing.position.set(0.08, 0.12, 0.0);
    this.rightWing.rotation.set(-0.35, -0.15, -0.55);
    this.body.add(this.rightWing);

    const rearGeo = new THREE.CylinderGeometry(0.006, 0.004, REAR_LEN, 5);
    const rearOffsets: Array<[number, number, number, number, number]> = [
      [-0.05, 0.03, 0.02, 0.7, 0.15],
      [0.05, 0.03, 0.02, -0.7, 0.15],
      [-0.04, 0.03, -0.08, 0.65, 0.55],
      [0.04, 0.03, -0.08, -0.65, 0.55],
    ];
    for (const [x, y, z, rotZ, rotX] of rearOffsets) {
      const leg = new THREE.Mesh(rearGeo, legMat);
      leg.position.set(x, y, z);
      leg.rotation.z = rotZ;
      leg.rotation.x = rotX;
      this.body.add(leg);
      this.midHind.push(leg);
    }

    this.leftArm = this.makeForelimb(legMat);
    this.rightArm = this.makeForelimb(legMat);

    // Head at +local Z; yaw PI so the fly faces the cabinet (-world Z).
    this.group.scale.setScalar(1.15);
    this.group.rotation.set(0.12, Math.PI, 0);
    this.baseY = 1.55;
    this.group.position.set(0, this.baseY, 1.04);
  }

  setContactTargets(_leftWorld: THREE.Vector3, _rightWorld: THREE.Vector3): void {}

  setScreenNormal(normalWorld: THREE.Vector3): void {
    this.screenNormal.copy(normalWorld).normalize();
  }

  setAimButton(_button: number | null): void {}

  setAimSensor(_sensor: string | null): void {}

  update(
    pose: Pose,
    elapsed: number,
    leftWorld: THREE.Vector3 | null = null,
    rightWorld: THREE.Vector3 | null = null,
  ): void {
    const aim = Math.max(-1, Math.min(1, pose.aim));
    const strike = Math.max(0, Math.min(1, pose.strike));
    const strikeL = Math.max(0, Math.min(1, pose.strike_l ?? strike));
    const strikeR = Math.max(0, Math.min(1, pose.strike_r ?? strike));
    const dt = Math.min(0.05, Math.max(0, elapsed - this.lastElapsed));
    this.lastElapsed = elapsed;
    const follow = 1 - Math.exp(-TIP_FOLLOW * dt);

    this.body.rotation.y = aim * 0.18;
    this.head.rotation.y = aim * 0.16;
    this.head.rotation.x = -0.08 - strike * 0.08;

    const buzz = Math.sin(elapsed * 52) * 0.35;
    this.leftWing.rotation.y = 0.15 + buzz;
    this.rightWing.rotation.y = -0.15 - buzz;
    this.leftWing.rotation.x = -0.35 + Math.sin(elapsed * 46) * 0.1;
    this.rightWing.rotation.x = -0.35 + Math.cos(elapsed * 46) * 0.1;

    this.group.position.y = this.baseY + Math.sin(elapsed * 3.2) * 0.004;
    this.group.position.x = aim * 0.02;

    this.group.updateWorldMatrix(true, false);

    this.aimTip(this._leftTarget, this.leftHip, leftWorld, strikeL);
    this.aimTip(this._rightTarget, this.rightHip, rightWorld, strikeR);
    if (!this.tipInitialized) {
      this.leftTip.copy(this._leftTarget);
      this.rightTip.copy(this._rightTarget);
      this.tipInitialized = true;
    } else {
      this.leftTip.lerp(this._leftTarget, follow);
      this.rightTip.lerp(this._rightTarget, follow);
    }

    this.plantArm(this.leftArm, this.leftHip, this.leftTip);
    this.plantArm(this.rightArm, this.rightHip, this.rightTip);
  }

  private makeForelimb(mat: THREE.MeshStandardMaterial): ForeLimb {
    const femur = new THREE.Mesh(
      new THREE.CylinderGeometry(0.007, 0.01, FEMUR_LEN, 6),
      mat,
    );
    const tibia = new THREE.Mesh(
      new THREE.CylinderGeometry(0.004, 0.007, TIBIA_LEN, 6),
      mat,
    );
    const hand = new THREE.Mesh(new THREE.SphereGeometry(0.012, 8, 6), mat);
    this.body.add(femur, tibia, hand);
    return { femur, tibia, hand };
  }

  private aimTip(
    out: THREE.Vector3,
    hipLocal: THREE.Vector3,
    padWorld: THREE.Vector3 | null,
    strike: number,
  ): void {
    this._hipWorld.copy(hipLocal);
    this.body.localToWorld(this._hipWorld);
    const hover = HOVER_AIR * (1 - strike) + HOVER_TAP * strike;
    if (padWorld) {
      out.copy(padWorld);
      out.addScaledVector(this.screenNormal, hover);
      return;
    }
    this._mid.copy(hipLocal);
    this._mid.x += hipLocal.x >= 0 ? 0.035 : -0.035;
    this._mid.y -= 0.055;
    this._mid.z += 0.06;
    this.body.localToWorld(this._mid);
    out.copy(this._mid);
    this._dir.copy(out).sub(this._hipWorld);
    const len = this._dir.length();
    if (len > MAX_REACH && len > 1e-6) {
      this._dir.multiplyScalar(MAX_REACH / len);
      out.copy(this._hipWorld).add(this._dir);
    }
  }

  private plantArm(limb: ForeLimb, hipLocal: THREE.Vector3, tipWorld: THREE.Vector3): void {
    this._from.copy(hipLocal);
    this._to.copy(tipWorld);
    this.body.worldToLocal(this._to);
    this._dir.copy(this._to).sub(this._from);
    let dist = this._dir.length();
    if (dist < 1e-5) {
      this._dir.set(0, -1, 0);
      dist = 0;
    } else {
      this._dir.multiplyScalar(1 / dist);
    }

    const reach = FEMUR_LEN + TIBIA_LEN;
    const side = hipLocal.x >= 0 ? 1 : -1;
    this._pole.set(side * 0.85, -1, -0.45);
    this._ortho.copy(this._pole).addScaledVector(this._dir, -this._pole.dot(this._dir));
    if (this._ortho.lengthSq() < 1e-8) {
      this._pole.set(0, 0, -1);
      this._ortho.copy(this._pole).addScaledVector(this._dir, -this._pole.dot(this._dir));
    }
    this._ortho.normalize();

    // Two-bone IK: elbow in the hip-tip / down-outward pole plane. If the pad
    // is beyond rest length, stretch both bones so the hand still plants.
    let along: number;
    let off: number;
    if (dist >= reach) {
      along = dist * (FEMUR_LEN / reach);
      off = Math.max(ELBOW_MIN, 0.08 * (reach / dist));
    } else {
      const folded = Math.max(dist, Math.abs(FEMUR_LEN - TIBIA_LEN) + 1e-4);
      along = (FEMUR_LEN * FEMUR_LEN + folded * folded - TIBIA_LEN * TIBIA_LEN) / (2 * folded);
      off = Math.sqrt(Math.max(1e-8, FEMUR_LEN * FEMUR_LEN - along * along));
    }

    this._elbow.copy(this._from).addScaledVector(this._dir, along).addScaledVector(this._ortho, off);
    this.plantSegment(limb.femur, this._from, this._elbow, FEMUR_LEN);
    this.plantSegment(limb.tibia, this._elbow, this._to, TIBIA_LEN);
    limb.hand.position.copy(this._to);
  }

  private plantSegment(
    mesh: THREE.Mesh,
    a: THREE.Vector3,
    b: THREE.Vector3,
    restLen: number,
  ): void {
    this._mid.copy(b).sub(a);
    const len = Math.max(0.02, this._mid.length());
    this._dir.copy(this._mid).multiplyScalar(1 / len);
    this._mid.copy(a).addScaledVector(this._dir, len * 0.5);
    mesh.position.copy(this._mid);
    mesh.scale.set(1, len / restLen, 1);
    mesh.quaternion.setFromUnitVectors(Y_AXIS, this._dir);
  }
}
