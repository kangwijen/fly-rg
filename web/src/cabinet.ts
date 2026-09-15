import * as THREE from "three";
import { ButtonRing, type ButtonLitState } from "./buttons";
import type { RingDisplay } from "./ring";

/** Screen disk radius in cabinet local units (matches CircleGeometry). */
export const SCREEN_RADIUS = 0.84;
/** Screen center in cabinet local space. */
export const SCREEN_LOCAL = new THREE.Vector3(0, 1.72, 0.66);

export class Cabinet {
  readonly group = new THREE.Group();
  readonly screenTexture: THREE.CanvasTexture;
  readonly buttons: ButtonRing;
  private screenMaterial: THREE.MeshBasicMaterial;
  private readonly _local = new THREE.Vector3();
  private readonly _normal = new THREE.Vector3();

  constructor(ring: RingDisplay) {
    this.screenTexture = new THREE.CanvasTexture(ring.canvas);
    this.screenTexture.colorSpace = THREE.SRGBColorSpace;
    this.screenTexture.minFilter = THREE.LinearFilter;
    this.screenTexture.magFilter = THREE.LinearFilter;
    this.screenTexture.generateMipmaps = false;
    this.screenTexture.flipY = true;

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

    const body = new THREE.Mesh(new THREE.BoxGeometry(2.55, 2.9, 1.15), bodyMat);
    body.position.set(0, 1.4, 0);
    this.group.add(body);

    const base = new THREE.Mesh(new THREE.BoxGeometry(2.8, 0.22, 1.4), accentMat);
    base.position.set(0, 0.11, 0.05);
    this.group.add(base);

    const bezel = new THREE.Mesh(new THREE.BoxGeometry(2.35, 2.35, 0.16), accentMat);
    bezel.position.set(0, 1.72, 0.54);
    this.group.add(bezel);

    this.screenMaterial = new THREE.MeshBasicMaterial({
      map: this.screenTexture,
      toneMapped: false,
    });
    const screen = new THREE.Mesh(
      new THREE.CircleGeometry(SCREEN_RADIUS, 64),
      this.screenMaterial,
    );
    screen.position.copy(SCREEN_LOCAL);
    this.group.add(screen);

    this.buttons = new ButtonRing();
    this.buttons.group.position.copy(SCREEN_LOCAL);
    this.buttons.group.position.z += 0.02;
    this.group.add(this.buttons.group);

    const outerTrim = new THREE.Mesh(
      new THREE.TorusGeometry(1.16, 0.028, 8, 64),
      trimMat,
    );
    outerTrim.position.set(0, SCREEN_LOCAL.y, SCREEN_LOCAL.z + 0.03);
    this.group.add(outerTrim);

    const leftRail = new THREE.Mesh(new THREE.BoxGeometry(0.08, 2.3, 0.08), magentaMat);
    leftRail.position.set(-1.22, 1.55, 0.58);
    this.group.add(leftRail);

    const rightRail = leftRail.clone();
    rightRail.position.x = 1.22;
    this.group.add(rightRail);

    const marque = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.18, 0.08), trimMat);
    marque.position.set(0, 2.85, 0.5);
    this.group.add(marque);

    this.group.rotation.x = -0.16;
  }

  setButtonStates(states: Record<string, ButtonLitState>): void {
    this.buttons.setStates(states);
  }

  sensorWorldPos(unitX: number, unitY: number, out = new THREE.Vector3()): THREE.Vector3 {
    this.group.updateWorldMatrix(true, false);
    this._local.set(
      unitX * SCREEN_RADIUS,
      SCREEN_LOCAL.y + unitY * SCREEN_RADIUS,
      SCREEN_LOCAL.z,
    );
    return out.copy(this.group.localToWorld(this._local));
  }

  screenNormalWorld(out = new THREE.Vector3()): THREE.Vector3 {
    this.group.updateWorldMatrix(true, false);
    this._normal.set(0, 0, 1);
    this._normal.transformDirection(this.group.matrixWorld);
    return out.copy(this._normal);
  }

  screenCenterWorld(out = new THREE.Vector3()): THREE.Vector3 {
    this.group.updateWorldMatrix(true, false);
    return out.copy(this.group.localToWorld(this._local.copy(SCREEN_LOCAL)));
  }

  updateTexture(): void {
    this.screenTexture.needsUpdate = true;
  }
}
