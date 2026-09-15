import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { Cabinet } from "./cabinet";
import { FruitFly } from "./fly";
import type { ActiveNote, Pose } from "./protocol";
import { RingDisplay } from "./ring";
import { buttonToSensor, pathPoint, sensorXY } from "./sensors";

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
  private aimSensor: string | null = "A5";
  private activeNotes: ActiveNote[] = [];
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

  setActiveNotes(notes: ActiveNote[]): void {
    this.activeNotes = notes;
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
    this.controls.dispose();
    this.resizeObserver.disconnect();
    this.renderer.dispose();
  }

  private syncFlyContacts(): void {
    const left = sensorXY("A4");
    const right = sensorXY("A5");
    this.cabinet.sensorWorldPos(left.x, left.y, this._leftIdle);
    this.cabinet.sensorWorldPos(right.x, right.y, this._rightIdle);
    this.cabinet.screenNormalWorld(this._normal);
    this.fly.setContactTargets(this._leftIdle, this._rightIdle);
    this.fly.setScreenNormal(this._normal);
  }

  /** Continuous tip target from the most urgent active note / slide. */
  private tipUnitXY(): { x: number; y: number } | null {
    const notes = this.activeNotes;
    if (notes.length === 0) {
      if (!this.aimSensor) return null;
      return sensorXY(this.aimSensor);
    }

    // Prefer slides in travel, then nearest-to-hit notes.
    let best: ActiveNote | null = null;
    let bestScore = -Infinity;
    for (const note of notes) {
      const progress = Math.min(1, Math.max(0, note.progress));
      const isSlide = note.type === "slide" && (note.path?.length ?? 0) > 1;
      const score = isSlide
        ? 100 + progress
        : progress >= 0.85
          ? 80 + progress
          : progress;
      if (score > bestScore) {
        bestScore = score;
        best = note;
      }
    }
    if (!best) {
      return this.aimSensor ? sensorXY(this.aimSensor) : null;
    }

    if (best.type === "slide" && best.path && best.path.length > 1) {
      const raw = Math.min(1, Math.max(0, best.progress));
      if (raw < 0.5) {
        const head = sensorXY(best.path[0]);
        const u = raw / 0.5;
        return { x: head.x * u, y: head.y * u };
      }
      return pathPoint(best.path, (raw - 0.5) / 0.5);
    }

    const sensor = best.sensor ?? this.aimSensor;
    if (!sensor) return null;
    const target = sensorXY(sensor);
    const progress = Math.min(1, Math.max(0, best.progress));
    // Ease toward the pad as the note arrives (not a hard teleport).
    return { x: target.x * progress, y: target.y * progress };
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

    let aimWorld: THREE.Vector3 | null = null;
    const tip = this.tipUnitXY();
    if (tip) {
      aimWorld = this.cabinet.sensorWorldPos(tip.x, tip.y, this._aimWorld);
    }
    this.fly.update(this.pose, elapsed, aimWorld);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  };
}
