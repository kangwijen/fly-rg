import * as THREE from "three";
import { sensorAngleRad } from "./sensors";

/**
 * Eight maimai DX A-ring buttons: raised annular-sector pads around the LCD.
 * Units match cabinet screen space (inner just outside the glass).
 */
const INNER_R = 0.88;
const OUTER_R = 1.12;
const GAP = 0.055;
const HALF_SPAN = Math.PI / 8 - GAP;
const DEPTH = 0.07;

export type ButtonLitState = {
  aim: boolean;
  tap: boolean;
  active: boolean;
  flashColor: number | null;
};

function annularSectorShape(
  inner: number,
  outer: number,
  a0: number,
  a1: number,
): THREE.Shape {
  const shape = new THREE.Shape();
  const steps = 18;
  shape.moveTo(Math.cos(a0) * outer, Math.sin(a0) * outer);
  for (let i = 1; i <= steps; i++) {
    const t = a0 + ((a1 - a0) * i) / steps;
    shape.lineTo(Math.cos(t) * outer, Math.sin(t) * outer);
  }
  for (let i = steps; i >= 0; i--) {
    const t = a0 + ((a1 - a0) * i) / steps;
    shape.lineTo(Math.cos(t) * inner, Math.sin(t) * inner);
  }
  shape.closePath();
  return shape;
}

export class ButtonRing {
  readonly group = new THREE.Group();
  private pads: Array<{
    mesh: THREE.Mesh;
    mat: THREE.MeshStandardMaterial;
    glow: THREE.Mesh;
    glowMat: THREE.MeshBasicMaterial;
    index: number;
  }> = [];

  constructor() {
    const housingMat = new THREE.MeshStandardMaterial({
      color: 0x1a2230,
      roughness: 0.45,
      metalness: 0.35,
    });
    // Torus sits in XY (screen plane). Do not rotate onto XZ.
    const housing = new THREE.Mesh(
      new THREE.TorusGeometry((INNER_R + OUTER_R) * 0.5, 0.13, 12, 64),
      housingMat,
    );
    housing.position.z = -0.02;
    this.group.add(housing);

    const plate = new THREE.Mesh(
      new THREE.RingGeometry(INNER_R - 0.03, OUTER_R + 0.04, 64),
      new THREE.MeshStandardMaterial({
        color: 0x0b1018,
        roughness: 0.75,
        metalness: 0.15,
        side: THREE.DoubleSide,
      }),
    );
    plate.position.z = -0.015;
    this.group.add(plate);

    for (let i = 1; i <= 8; i++) {
      const mid = sensorAngleRad("A", i);
      const a0 = mid - HALF_SPAN;
      const a1 = mid + HALF_SPAN;
      const shape = annularSectorShape(INNER_R, OUTER_R, a0, a1);
      const geo = new THREE.ExtrudeGeometry(shape, {
        depth: DEPTH,
        bevelEnabled: true,
        bevelThickness: 0.014,
        bevelSize: 0.012,
        bevelSegments: 3,
        curveSegments: 10,
      });
      geo.computeVertexNormals();

      const mat = new THREE.MeshStandardMaterial({
        color: 0xf2f5fa,
        emissive: 0x1a3040,
        emissiveIntensity: 0.12,
        roughness: 0.28,
        metalness: 0.06,
      });
      const mesh = new THREE.Mesh(geo, mat);

      const glowMat = new THREE.MeshBasicMaterial({
        color: 0x3de0d0,
        transparent: true,
        opacity: 0,
        side: THREE.DoubleSide,
      });
      const glow = new THREE.Mesh(
        new THREE.RingGeometry(INNER_R + 0.02, OUTER_R - 0.02, 24, 1, a0, a1 - a0),
        glowMat,
      );
      glow.position.z = DEPTH + 0.008;

      const label = this.makeLabel(`A${i}`);
      const lx = Math.cos(mid) * ((INNER_R + OUTER_R) * 0.5);
      const ly = Math.sin(mid) * ((INNER_R + OUTER_R) * 0.5);
      label.position.set(lx, ly, DEPTH + 0.02);

      this.group.add(mesh, glow, label);
      this.pads.push({ mesh, mat, glow, glowMat, index: i });
    }
  }

  setStates(states: Record<string, ButtonLitState>): void {
    for (const pad of this.pads) {
      const key = `A${pad.index}`;
      const st = states[key] ?? {
        aim: false,
        tap: false,
        active: false,
        flashColor: null,
      };
      if (st.flashColor != null) {
        pad.mat.emissive.setHex(st.flashColor);
        pad.mat.emissiveIntensity = 0.95;
        pad.mat.color.setHex(0xffffff);
        pad.glowMat.color.setHex(st.flashColor);
        pad.glowMat.opacity = 0.55;
        pad.mesh.position.z = 0;
      } else if (st.tap) {
        pad.mat.emissive.setHex(0x3de0d0);
        pad.mat.emissiveIntensity = 0.85;
        pad.mat.color.setHex(0xffffff);
        pad.glowMat.color.setHex(0x3de0d0);
        pad.glowMat.opacity = 0.4;
        pad.mesh.position.z = -0.012;
      } else if (st.aim) {
        pad.mat.emissive.setHex(0xe24f9c);
        pad.mat.emissiveIntensity = 0.55;
        pad.mat.color.setHex(0xfff4fa);
        pad.glowMat.color.setHex(0xe24f9c);
        pad.glowMat.opacity = 0.28;
        pad.mesh.position.z = 0;
      } else if (st.active) {
        pad.mat.emissive.setHex(0x3de0d0);
        pad.mat.emissiveIntensity = 0.35;
        pad.mat.color.setHex(0xeef6ff);
        pad.glowMat.color.setHex(0x3de0d0);
        pad.glowMat.opacity = 0.18;
        pad.mesh.position.z = 0;
      } else {
        pad.mat.emissive.setHex(0x1a3040);
        pad.mat.emissiveIntensity = 0.12;
        pad.mat.color.setHex(0xf2f5fa);
        pad.glowMat.opacity = 0;
        pad.mesh.position.z = 0;
      }
    }
  }

  private makeLabel(text: string): THREE.Sprite {
    const c = document.createElement("canvas");
    c.width = 128;
    c.height = 64;
    const ctx = c.getContext("2d");
    if (ctx) {
      ctx.clearRect(0, 0, 128, 64);
      ctx.fillStyle = "rgba(8, 12, 20, 0.65)";
      ctx.fillRect(24, 12, 80, 40);
      ctx.fillStyle = "#e8f0fa";
      ctx.font = "700 28px IBM Plex Mono, monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(text, 64, 34);
    }
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    const mat = new THREE.SpriteMaterial({
      map: tex,
      transparent: true,
      depthTest: true,
    });
    const spr = new THREE.Sprite(mat);
    spr.scale.set(0.18, 0.09, 1);
    return spr;
  }
}
