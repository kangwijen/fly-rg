import * as THREE from "three";
import type { Pose } from "./protocol";

const LEG_LEN = 0.16;
const PRESS_DEPTH = 0.022;
const TIP_FOLLOW = 8.5; // higher = snappier, still smooth (1/s exponential)
const Y_AXIS = new THREE.Vector3(0, 1, 0);

/**
 * Drosophila-style fruit fly: head toward the cabinet glass, six legs,
 * large red eyes, translucent wings. Foreleg tips stay on the screen plane
 * and smoothly chase note/slide targets (no hard snaps).
 */
export class FruitFly {
  readonly group = new THREE.Group();
  private body: THREE.Group;
  private head: THREE.Mesh;
  private leftWing: THREE.Mesh;
  private rightWing: THREE.Mesh;
  private midHind: THREE.Mesh[] = [];
  private foreLeft: THREE.Mesh;
  private foreRight: THREE.Mesh;
  private leftHip = new THREE.Vector3(-0.045, 0.04, 0.055);
  private rightHip = new THREE.Vector3(0.045, 0.04, 0.055);
  private leftIdle = new THREE.Vector3();
  private rightIdle = new THREE.Vector3();
  private leftTip = new THREE.Vector3();
  private rightTip = new THREE.Vector3();
  private tipInitialized = false;
  private hasContacts = false;
  private screenNormal = new THREE.Vector3(0, 0, 1);
  private readonly _dir = new THREE.Vector3();
  private readonly _mid = new THREE.Vector3();
  private readonly _leftTarget = new THREE.Vector3();
  private readonly _rightTarget = new THREE.Vector3();
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

    const legGeo = new THREE.CylinderGeometry(0.006, 0.004, LEG_LEN, 5);
    const rearOffsets: Array<[number, number, number, number, number]> = [
      [-0.05, 0.03, 0.02, 0.7, 0.15],
      [0.05, 0.03, 0.02, -0.7, 0.15],
      [-0.04, 0.03, -0.08, 0.65, 0.55],
      [0.04, 0.03, -0.08, -0.65, 0.55],
    ];
    for (const [x, y, z, rotZ, rotX] of rearOffsets) {
      const leg = new THREE.Mesh(legGeo, legMat);
      leg.position.set(x, y, z);
      leg.rotation.z = rotZ;
      leg.rotation.x = rotX;
      this.body.add(leg);
      this.midHind.push(leg);
    }

    this.foreLeft = new THREE.Mesh(legGeo.clone(), legMat);
    this.foreRight = new THREE.Mesh(legGeo.clone(), legMat);
    this.body.add(this.foreLeft);
    this.body.add(this.foreRight);

    // Head at +local Z; yaw PI so the fly faces the cabinet (-world Z).
    this.group.scale.setScalar(1.15);
    this.group.rotation.set(0.08, Math.PI + 0.18, 0);
    this.baseY = 1.58;
    this.group.position.set(-0.42, this.baseY, 1.45);
  }

  setContactTargets(leftWorld: THREE.Vector3, rightWorld: THREE.Vector3): void {
    this.leftIdle.copy(leftWorld);
    this.rightIdle.copy(rightWorld);
    this.hasContacts = true;
    if (!this.tipInitialized) {
      this.leftTip.copy(leftWorld);
      this.rightTip.copy(rightWorld);
      this.tipInitialized = true;
    }
  }

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
    const alpha = 1 - Math.exp(-TIP_FOLLOW * dt);

    this.body.rotation.y = aim * 0.18;
    this.head.rotation.y = aim * 0.16;
    this.head.rotation.x = -0.08 - strike * 0.08;

    const buzz = Math.sin(elapsed * 52) * 0.35;
    this.leftWing.rotation.y = 0.15 + buzz;
    this.rightWing.rotation.y = -0.15 - buzz;
    this.leftWing.rotation.x = -0.35 + Math.sin(elapsed * 46) * 0.1;
    this.rightWing.rotation.x = -0.35 + Math.cos(elapsed * 46) * 0.1;

    this.group.position.y = this.baseY + Math.sin(elapsed * 3.2) * 0.004;
    this.group.position.x = -0.42 + aim * 0.03;

    if (!this.hasContacts || !this.tipInitialized) return;

    this.group.updateWorldMatrix(true, false);

    this._leftTarget.copy(leftWorld ?? this.leftIdle);
    this._rightTarget.copy(rightWorld ?? this.rightIdle);
    this._leftTarget.addScaledVector(this.screenNormal, -PRESS_DEPTH * strikeL);
    this._rightTarget.addScaledVector(this.screenNormal, -PRESS_DEPTH * strikeR);

    this.leftTip.lerp(this._leftTarget, alpha);
    this.rightTip.lerp(this._rightTarget, alpha);

    this.plantLeg(this.foreLeft, this.leftHip, this.leftTip);
    this.plantLeg(this.foreRight, this.rightHip, this.rightTip);
  }

  private plantLeg(leg: THREE.Mesh, hipLocal: THREE.Vector3, tipWorld: THREE.Vector3): void {
    this._mid.copy(tipWorld);
    this.body.worldToLocal(this._mid);
    this._dir.copy(this._mid).sub(hipLocal);
    const len = Math.max(0.06, this._dir.length());
    this._dir.multiplyScalar(1 / len);
    this._mid.copy(hipLocal).addScaledVector(this._dir, len * 0.5);
    leg.position.copy(this._mid);
    leg.scale.set(1, len / LEG_LEN, 1);
    leg.quaternion.setFromUnitVectors(Y_AXIS, this._dir);
  }
}
