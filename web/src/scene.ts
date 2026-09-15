import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { Cabinet } from "./cabinet";
import { FruitFly } from "./fly";
import type { ActiveNote, Pose } from "./protocol";
import { RingDisplay } from "./ring";
import { sensorXY } from "./sensors";

/** Idle homes on the unit disk: left A6, right A3. */
const HOME_L = sensorXY("A6");
const HOME_R = sensorXY("A3");

function isUnitXY(value: unknown): value is [number, number] {
  return (
    Array.isArray(value) &&
    value.length >= 2 &&
    Number.isFinite(value[0]) &&
    Number.isFinite(value[1])
  );
}

export class ArcadeScene {
  readonly ring = new RingDisplay();
  readonly cabinet: Cabinet;
  readonly fly: FruitFly;

  private renderer: THREE.WebGLRenderer;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private controls: OrbitControls;
  private clock = new THREE.Clock();
  private pose: Pose = { aim: 0, strike: 0 };
  private running = false;
  private viewport: HTMLElement;
  private resizeObserver: ResizeObserver;
  private handLXY: [number, number] | null = null;
  private handRXY: [number, number] | null = null;
  private readonly _leftAim = new THREE.Vector3();
  private readonly _rightAim = new THREE.Vector3();
  private readonly _normal = new THREE.Vector3();
  private readonly _lookAt = new THREE.Vector3();

  constructor(canvas: HTMLCanvasElement, viewport: HTMLElement) {
    this.viewport = viewport;
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x05070c);
    this.scene.fog = new THREE.Fog(0x05070c, 10, 28);

    this.camera = new THREE.PerspectiveCamera(40, 1, 0.1, 50);

    const ambient = new THREE.AmbientLight(0x6a7d96, 0.55);
    this.scene.add(ambient);

    const key = new THREE.DirectionalLight(0xfff2e0, 1.45);
    key.position.set(3.2, 5.2, 4.2);
    this.scene.add(key);

    const fill = new THREE.DirectionalLight(0x3de0d0, 0.4);
    fill.position.set(-3.5, 2.8, 2.8);
    this.scene.add(fill);

    const rim = new THREE.PointLight(0xe24f9c, 0.55, 14);
    rim.position.set(-1.4, 2.6, -0.6);
    this.scene.add(rim);

    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(9, 48),
      new THREE.MeshStandardMaterial({
        color: 0x0a1018,
        roughness: 0.92,
        metalness: 0.05,
      }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = 0;
    this.scene.add(floor);

    const floorGlow = new THREE.Mesh(
      new THREE.RingGeometry(1.6, 3.4, 48),
      new THREE.MeshBasicMaterial({
        color: 0x123048,
        transparent: true,
        opacity: 0.35,
        side: THREE.DoubleSide,
      }),
    );
    floorGlow.rotation.x = -Math.PI / 2;
    floorGlow.position.y = 0.01;
    this.scene.add(floorGlow);

    this.cabinet = new Cabinet(this.ring);
    this.scene.add(this.cabinet.group);

    this.fly = new FruitFly();
    this.scene.add(this.fly.group);

    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.enablePan = true;
    this.controls.minDistance = 1.6;
    this.controls.maxDistance = 8;
    this.controls.minPolarAngle = 0.35;
    this.controls.maxPolarAngle = Math.PI * 0.62;
    this.controls.target.set(0, 1.55, 0.45);

    this.syncFlyContacts();
    this.frameCamera();
    this.onResize();

    this.resizeObserver = new ResizeObserver(() => this.onResize());
    this.resizeObserver.observe(this.viewport);
  }

  setPose(pose: Pose): void {
    this.pose = pose;
  }

  setActiveNotes(_notes: ActiveNote[]): void {}

  setHands(
    left?: [number, number] | null,
    right?: [number, number] | null,
  ): void {
    this.handLXY = isUnitXY(left) ? left : null;
    this.handRXY = isUnitXY(right) ? right : null;
  }

  setAimSensor(sensor: string | null): void {
    if (sensor) this.fly.setAimSensor(sensor);
  }

  setAimButton(button: number | null): void {
    if (button == null) return;
    this.fly.setAimButton(button);
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.renderer.setAnimationLoop(this.tick);
  }

  stop(): void {
    this.running = false;
    this.renderer.setAnimationLoop(null);
  }

  dispose(): void {
    this.stop();
    this.controls.dispose();
    this.resizeObserver.disconnect();
    this.renderer.dispose();
  }

  private handUnit(
    xy: [number, number] | null,
    home: { x: number; y: number },
  ): { x: number; y: number } {
    if (xy) return { x: xy[0], y: xy[1] };
    return home;
  }

  private syncFlyContacts(): void {
    const left = this.handUnit(this.handLXY, HOME_L);
    const right = this.handUnit(this.handRXY, HOME_R);
    this.cabinet.sensorWorldPos(left.x, left.y, this._leftAim);
    this.cabinet.sensorWorldPos(right.x, right.y, this._rightAim);
    this.cabinet.screenNormalWorld(this._normal);
    this.fly.setContactTargets(this._leftAim, this._rightAim);
    this.fly.setScreenNormal(this._normal);
    this.fly.leanToward(this._leftAim, this._rightAim);
  }

  /** Default 3/4 view from behind-right, looking over the fly at the playfield. */
  private frameCamera(): void {
    this.cabinet.screenCenterWorld(this._lookAt);
    this.controls.target.copy(this._lookAt);
    this.controls.target.y -= 0.05;
    // Behind and to the right of the fly (not top-down).
    this.camera.position.set(1.85, 1.95, 3.35);
    this.controls.update();
  }

  private onResize = (): void => {
    const w = Math.max(1, this.viewport.clientWidth);
    const h = Math.max(1, this.viewport.clientHeight);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h, false);
  };

  private tick = (): void => {
    const elapsed = this.clock.getElapsedTime();
    this.ring.draw(performance.now());
    this.cabinet.updateTexture();
    this.cabinet.setButtonStates(this.ring.getAButtonStates(performance.now()));
    this.syncFlyContacts();
    this.fly.update(this.pose, elapsed);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  };
}
