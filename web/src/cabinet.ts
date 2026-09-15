import * as THREE from "three";
import type { RingDisplay } from "./ring";

export class Cabinet {
  readonly group = new THREE.Group();
  readonly screenTexture: THREE.CanvasTexture;
  private screenMaterial: THREE.MeshBasicMaterial;

  constructor(ring: RingDisplay) {
    this.screenTexture = new THREE.CanvasTexture(ring.canvas);
    this.screenTexture.colorSpace = THREE.SRGBColorSpace;
    this.screenTexture.minFilter = THREE.LinearFilter;
    this.screenTexture.magFilter = THREE.LinearFilter;

    const bodyMat = new THREE.MeshStandardMaterial({
      color: 0x121826,
      roughness: 0.72,
      metalness: 0.18,
    });
    const accentMat = new THREE.MeshStandardMaterial({
      color: 0x1d2a3f,
      roughness: 0.55,
      metalness: 0.25,
    });
    const trimMat = new THREE.MeshStandardMaterial({
      color: 0x3de0d0,
      emissive: 0x0a3a36,
      emissiveIntensity: 0.35,
      roughness: 0.4,
      metalness: 0.4,
    });
    const magentaMat = new THREE.MeshStandardMaterial({
      color: 0xe24f9c,
      emissive: 0x3a1028,
      emissiveIntensity: 0.25,
      roughness: 0.45,
      metalness: 0.35,
    });

    const body = new THREE.Mesh(new THREE.BoxGeometry(2.4, 2.8, 1.1), bodyMat);
    body.position.set(0, 1.4, 0);
    this.group.add(body);

    const base = new THREE.Mesh(new THREE.BoxGeometry(2.7, 0.22, 1.35), accentMat);
    base.position.set(0, 0.11, 0.05);
    this.group.add(base);

    const bezel = new THREE.Mesh(new THREE.BoxGeometry(2.05, 2.05, 0.12), accentMat);
    bezel.position.set(0, 1.7, 0.56);
    this.group.add(bezel);

    const bezelRing = new THREE.Mesh(
      new THREE.TorusGeometry(0.92, 0.05, 8, 32),
      trimMat,
    );
    bezelRing.position.set(0, 1.7, 0.63);
    this.group.add(bezelRing);

    this.screenMaterial = new THREE.MeshBasicMaterial({
      map: this.screenTexture,
    });
    const screen = new THREE.Mesh(
      new THREE.CircleGeometry(0.86, 48),
      this.screenMaterial,
    );
    screen.position.set(0, 1.7, 0.64);
    this.group.add(screen);

    const leftRail = new THREE.Mesh(new THREE.BoxGeometry(0.08, 2.2, 0.08), magentaMat);
    leftRail.position.set(-1.15, 1.55, 0.58);
    this.group.add(leftRail);

    const rightRail = leftRail.clone();
    rightRail.position.x = 1.15;
    this.group.add(rightRail);

    const marque = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.18, 0.08), trimMat);
    marque.position.set(0, 2.75, 0.5);
    this.group.add(marque);

    // Slight forward tilt like a real cabinet
    this.group.rotation.x = -0.12;
  }

  updateTexture(): void {
    this.screenTexture.needsUpdate = true;
  }
}
