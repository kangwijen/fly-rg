import * as THREE from "three";
import { Cabinet } from "./cabinet";
import { FruitFly } from "./fly";
import type { Pose } from "./protocol";
import { RingDisplay } from "./ring";
import { buttonToSensor, sensorXY } from "./sensors";

export class ArcadeScene {
  readonly ring = new RingDisplay();
  readonly cabinet: Cabinet;
  readonly fly: FruitFly;

  private renderer: THREE.WebGLRenderer;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private clock = new THREE.Clock();
  private pose: Pose = { aim: 0, strike: 0 };
  private running = false;
  private viewport: HTMLElement;
  private resizeObserver: ResizeObserver;
  private aimSensor: string | null = "A5";
  private readonly _aimWorld = new THREE.Vector3();
  private readonly _normal = new THREE.Vector3();
  private readonly _lookAt = new THREE.Vector3();
  private readonly _leftIdle = new THREE.Vector3();
  private readonly _rightIdle = new THREE.Vector3();

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
    this.scene.fog = new THREE.Fog(0x05070c, 8, 22);

    this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 50);

    const ambient = new THREE.AmbientLight(0x6a7d96, 0.55);
    this.scene.add(ambient);

    const key = new THREE.DirectionalLight(0xfff2e0, 1.35);
    key.position.set(2.2, 5.5, 4.5);
    this.scene.add(key);

    const fill = new THREE.DirectionalLight(0x3de0d0, 0.35);
    fill.position.set(-3.5, 2.5, 2.5);
    this.scene.add(fill);

    const rim = new THREE.PointLight(0xe24f9c, 0.55, 12);
    rim.position.set(-1.2, 2.4, -0.8);
    this.scene.add(rim);

    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(8, 48),
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
      new THREE.RingGeometry(1.6, 3.2, 48),
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

    this.syncFlyContacts();
    this.frameCamera();
    this.onResize();

    this.resizeObserver = new ResizeObserver(() => this.onResize());
    this.resizeObserver.observe(this.viewport);
  }

  setPose(pose: Pose): void {
    this.pose = pose;
  }

  setAimSensor(sensor: string | null): void {
    this.aimSensor = sensor;
    if (sensor) this.fly.setAimSensor(sensor);
  }

  setAimButton(button: number | null): void {
    if (button == null) return;
    this.aimSensor = buttonToSensor(button);
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
    this.resizeObserver.disconnect();
    this.renderer.dispose();
  }

  private syncFlyContacts(): void {
    // Fly faces -Z into the glass (yaw PI): anatomical left reaches +screen X (A4).
    const left = sensorXY("A4");
    const right = sensorXY("A5");
    this.cabinet.sensorWorldPos(left.x, left.y, this._leftIdle);
    this.cabinet.sensorWorldPos(right.x, right.y, this._rightIdle);
    this.cabinet.screenNormalWorld(this._normal);
    this.fly.setContactTargets(this._leftIdle, this._rightIdle);
    this.fly.setScreenNormal(this._normal);
  }

  private frameCamera(): void {
    this.cabinet.screenCenterWorld(this._lookAt);
    // Over-shoulder: camera behind fly, looking into the playfield screen.
    this.camera.position.set(0.05, 2.05, 2.95);
    this.camera.lookAt(this._lookAt.x, this._lookAt.y - 0.05, this._lookAt.z);
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
    this.syncFlyContacts();

    let aimWorld: THREE.Vector3 | null = null;
    if (this.aimSensor) {
      const xy = sensorXY(this.aimSensor);
      aimWorld = this.cabinet.sensorWorldPos(xy.x, xy.y, this._aimWorld);
    }
    this.fly.update(this.pose, elapsed, aimWorld);
    this.renderer.render(this.scene, this.camera);
  };
}
