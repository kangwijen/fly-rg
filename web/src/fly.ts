import * as THREE from "three";
import type { Pose } from "./protocol";

function buttonAngle(button: number): number {
  return -Math.PI / 2 + ((button - 1) % 8) * (Math.PI / 4);
}

export class FruitFly {
  readonly group = new THREE.Group();
  private body: THREE.Group;
  private head: THREE.Mesh;
  private leftWing: THREE.Mesh;
  private rightWing: THREE.Mesh;
  private legs: THREE.Mesh[] = [];
  private foreLeft: THREE.Mesh;
  private foreRight: THREE.Mesh;
  private aimButton = 1;

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

    const legGeo = new THREE.CylinderGeometry(0.012, 0.01, 0.22, 5);
    const legOffsets: Array<[number, number, number]> = [
      [-0.1, 0.12, 0.18],
      [0.1, 0.12, 0.18],
      [-0.12, 0.1, 0.02],
      [0.12, 0.1, 0.02],
      [-0.1, 0.1, -0.14],
      [0.1, 0.1, -0.14],
    ];

    for (const [x, y, z] of legOffsets) {
      const leg = new THREE.Mesh(legGeo, legMat);
      leg.position.set(x, y, z);
      leg.rotation.z = x < 0 ? 0.55 : -0.55;
      leg.rotation.x = z > 0.1 ? -0.35 : z < 0 ? 0.4 : 0.1;
      this.body.add(leg);
      this.legs.push(leg);
    }

    this.foreLeft = this.legs[0];
    this.foreRight = this.legs[1];

    this.group.position.set(0, 0, 1.55);
  }

  setAimButton(button: number | null): void {
    if (button == null) return;
    this.aimButton = Math.max(1, Math.min(8, button));
  }

  update(pose: Pose, elapsed: number): void {
    const aim = Math.max(-1, Math.min(1, pose.aim));
    const strike = Math.max(0, Math.min(1, pose.strike));

    this.body.rotation.y = aim * 0.55;
    this.head.rotation.y = aim * 0.35;
    this.head.rotation.x = -0.1 - strike * 0.15;

    const buzz = Math.sin(elapsed * 55) * 0.45;
    this.leftWing.rotation.y = -0.2 + buzz;
    this.rightWing.rotation.y = 0.2 - buzz;
    this.leftWing.rotation.x = 0.15 + Math.sin(elapsed * 48) * 0.12;
    this.rightWing.rotation.x = 0.15 + Math.cos(elapsed * 48) * 0.12;

    const angle = buttonAngle(this.aimButton);
    // Map ring angle (screen plane) to punch yaw around body up-axis
    const punchYaw = angle + Math.PI / 2;
    const side = Math.cos(punchYaw) >= 0 ? 1 : -1;
    const fore = side >= 0 ? this.foreRight : this.foreLeft;
    const other = side >= 0 ? this.foreLeft : this.foreRight;

    const punchReach = strike * 0.55;
    fore.rotation.x = -0.35 - punchReach * 1.1;
    fore.rotation.z = (side >= 0 ? -0.55 : 0.55) + side * punchReach * 0.35;
    fore.position.z = 0.18 + punchReach * 0.12;
    fore.position.y = 0.12 + strike * 0.04;

    other.rotation.x = -0.25 + strike * 0.1;
    other.position.z = 0.18;
    other.position.y = 0.12;

    this.group.position.y = Math.sin(elapsed * 3.2) * 0.012;
  }
}
