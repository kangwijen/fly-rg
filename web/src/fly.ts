import * as THREE from "three";
import type { Pose } from "./protocol";
import { buttonToSensor, sensorXY } from "./sensors";

const LEG_LEN = 0.28;
const PRESS_DEPTH = 0.028;
const Y_AXIS = new THREE.Vector3(0, 1, 0);

/**
 * Low-poly fly between camera and cabinet, head toward the screen glass.
 * Both foreleg tips stay on the screen plane; strike presses the active tip inward.
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
  private leftHip = new THREE.Vector3(-0.1, 0.16, 0.2);
  private rightHip = new THREE.Vector3(0.1, 0.16, 0.2);
  private leftContact = new THREE.Vector3();
  private rightContact = new THREE.Vector3();
  private hasContacts = false;
  private aimSensor = "A5";
  private screenNormal = new THREE.Vector3(0, 0, 1);
  private readonly _leftTip = new THREE.Vector3();
  private readonly _rightTip = new THREE.Vector3();
  private readonly _dir = new THREE.Vector3();
  private readonly _mid = new THREE.Vector3();
  private baseY = 0;

  constructor() {
    const bodyMat = new THREE.MeshStandardMaterial({
      color: 0x2a2418,
      roughness: 0.65,
      metalness: 0.05,
    });
    const thoraxMat = new THREE.MeshStandardMaterial({
      color: 0x3a3224,
      roughness: 0.55,
      metalness: 0.08,
    });
    const wingMat = new THREE.MeshStandardMaterial({
      color: 0xa8d8e8,
      transparent: true,
      opacity: 0.45,
      roughness: 0.3,
      metalness: 0.05,
      side: THREE.DoubleSide,
    });
    const eyeMat = new THREE.MeshStandardMaterial({
      color: 0xc04030,
      emissive: 0x401010,
      emissiveIntensity: 0.4,
      roughness: 0.35,
    });
    const legMat = new THREE.MeshStandardMaterial({
      color: 0x1a1610,
      roughness: 0.7,
    });

    this.body = new THREE.Group();
    this.group.add(this.body);

    const abdomen = new THREE.Mesh(new THREE.SphereGeometry(0.18, 12, 10), bodyMat);
    abdomen.scale.set(1.1, 0.85, 1.6);
    abdomen.position.set(0, 0.22, -0.08);
    this.body.add(abdomen);

    const thorax = new THREE.Mesh(new THREE.SphereGeometry(0.14, 12, 10), thoraxMat);
    thorax.scale.set(1.05, 0.9, 1.15);
    thorax.position.set(0, 0.26, 0.12);
    this.body.add(thorax);

    this.head = new THREE.Mesh(new THREE.SphereGeometry(0.1, 12, 10), thoraxMat);
    this.head.position.set(0, 0.28, 0.28);
    this.body.add(this.head);

    const leftEye = new THREE.Mesh(new THREE.SphereGeometry(0.045, 8, 8), eyeMat);
    leftEye.position.set(-0.07, 0.02, 0.06);
    this.head.add(leftEye);
    const rightEye = leftEye.clone();
    rightEye.position.x = 0.07;
    this.head.add(rightEye);

    this.leftWing = new THREE.Mesh(new THREE.PlaneGeometry(0.28, 0.14), wingMat);
    this.leftWing.position.set(-0.12, 0.34, 0.05);
    this.leftWing.rotation.z = 0.35;
    this.body.add(this.leftWing);

    this.rightWing = new THREE.Mesh(new THREE.PlaneGeometry(0.28, 0.14), wingMat);
    this.rightWing.position.set(0.12, 0.34, 0.05);
    this.rightWing.rotation.z = -0.35;
    this.body.add(this.rightWing);

    const legGeo = new THREE.CylinderGeometry(0.012, 0.01, LEG_LEN, 5);
    const rearOffsets: Array<[number, number, number]> = [
      [-0.13, 0.1, 0.02],
      [0.13, 0.1, 0.02],
      [-0.1, 0.1, -0.14],
      [0.1, 0.1, -0.14],
    ];

    for (const [x, y, z] of rearOffsets) {
      const leg = new THREE.Mesh(legGeo, legMat);
      leg.position.set(x, y, z);
      leg.rotation.z = x < 0 ? 0.55 : -0.55;
      leg.rotation.x = z < 0 ? 0.4 : 0.1;
      this.body.add(leg);
      this.midHind.push(leg);
    }

    this.foreLeft = new THREE.Mesh(legGeo.clone(), legMat);
    this.foreRight = new THREE.Mesh(legGeo.clone(), legMat);
    this.body.add(this.foreLeft);
    this.body.add(this.foreRight);

    // Head at +local Z; yaw PI so head faces the cabinet screen (-world Z).
    this.group.scale.setScalar(1.25);
    this.group.rotation.set(0.18, Math.PI, 0);
    this.baseY = 1.52;
    this.group.position.set(0, this.baseY, 1.18);
  }

  /** Idle / resting tip targets on the glass (world space). */
  setContactTargets(leftWorld: THREE.Vector3, rightWorld: THREE.Vector3): void {
    this.leftContact.copy(leftWorld);
    this.rightContact.copy(rightWorld);
    this.hasContacts = true;
  }

  setScreenNormal(normalWorld: THREE.Vector3): void {
    this.screenNormal.copy(normalWorld).normalize();
  }

  setAimButton(button: number | null): void {
    if (button == null) return;
    this.aimSensor = buttonToSensor(Math.max(1, Math.min(8, button)));
  }

  setAimSensor(sensor: string | null): void {
    if (!sensor) return;
    this.aimSensor = sensor;
  }

  update(pose: Pose, elapsed: number, aimWorld: THREE.Vector3 | null = null): void {
    const aim = Math.max(-1, Math.min(1, pose.aim));
    const strike = Math.max(0, Math.min(1, pose.strike));

    this.body.rotation.y = aim * 0.22;
    this.head.rotation.y = aim * 0.18;
    this.head.rotation.x = -0.12 - strike * 0.1;

    const buzz = Math.sin(elapsed * 55) * 0.45;
    this.leftWing.rotation.y = -0.2 + buzz;
    this.rightWing.rotation.y = 0.2 - buzz;
    this.leftWing.rotation.x = 0.15 + Math.sin(elapsed * 48) * 0.12;
    this.rightWing.rotation.x = 0.15 + Math.cos(elapsed * 48) * 0.12;

    this.group.position.y = this.baseY + Math.sin(elapsed * 3.2) * 0.006;
    this.group.position.x = aim * 0.04;

    if (!this.hasContacts) return;

    this.group.updateWorldMatrix(true, false);

    this._leftTip.copy(this.leftContact);
    this._rightTip.copy(this.rightContact);

    // After yaw PI (facing cabinet), pick the nearer tip rather than raw screen X.
    const pressLeft = aimWorld
      ? this.leftContact.distanceToSquared(aimWorld) <=
        this.rightContact.distanceToSquared(aimWorld)
      : sensorXY(this.aimSensor).x > 0;

    if (aimWorld) {
      if (pressLeft) {
        this._leftTip.lerp(aimWorld, 0.85 + strike * 0.15);
        this._leftTip.addScaledVector(this.screenNormal, -PRESS_DEPTH * strike);
      } else {
        this._rightTip.lerp(aimWorld, 0.85 + strike * 0.15);
        this._rightTip.addScaledVector(this.screenNormal, -PRESS_DEPTH * strike);
      }
    } else if (strike > 0.01) {
      const active = pressLeft ? this._leftTip : this._rightTip;
      active.addScaledVector(this.screenNormal, -PRESS_DEPTH * strike);
    }

    this.plantLeg(this.foreLeft, this.leftHip, this._leftTip);
    this.plantLeg(this.foreRight, this.rightHip, this._rightTip);
  }

  private plantLeg(leg: THREE.Mesh, hipLocal: THREE.Vector3, tipWorld: THREE.Vector3): void {
    this._mid.copy(tipWorld);
    this.body.worldToLocal(this._mid);
    this._dir.copy(this._mid).sub(hipLocal);
    const len = Math.max(0.08, this._dir.length());
    this._dir.multiplyScalar(1 / len);
    this._mid.copy(hipLocal).addScaledVector(this._dir, len * 0.5);
    leg.position.copy(this._mid);
    leg.scale.set(1, len / LEG_LEN, 1);
    leg.quaternion.setFromUnitVectors(Y_AXIS, this._dir);
  }
}
