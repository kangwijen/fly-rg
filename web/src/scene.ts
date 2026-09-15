import * as THREE from "three";
import { Cabinet } from "./cabinet";
import { FruitFly } from "./fly";
import type { Pose } from "./protocol";
import { RingDisplay } from "./ring";

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

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(window.innerWidth, window.innerHeight, false);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x05070c);
    this.scene.fog = new THREE.Fog(0x05070c, 8, 22);

    this.camera = new THREE.PerspectiveCamera(
      42,
      window.innerWidth / window.innerHeight,
      0.1,
      50,
    );
    // Three-quarter view: fly + cabinet screen visible
    this.camera.position.set(2.6, 2.35, 4.2);
    this.camera.lookAt(0.1, 1.35, 0.4);

    const ambient = new THREE.AmbientLight(0x6a7d96, 0.55);
    this.scene.add(ambient);

    const key = new THREE.DirectionalLight(0xfff2e0, 1.35);
    key.position.set(3.5, 6, 4);
    this.scene.add(key);

    const fill = new THREE.DirectionalLight(0x3de0d0, 0.35);
    fill.position.set(-4, 2.5, 1.5);
    this.scene.add(fill);

    const rim = new THREE.PointLight(0xe24f9c, 0.55, 12);
    rim.position.set(-1.5, 2.2, -1.2);
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

    window.addEventListener("resize", this.onResize);
  }

  setPose(pose: Pose): void {
    this.pose = pose;
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
    window.removeEventListener("resize", this.onResize);
    this.renderer.dispose();
  }

  private onResize = (): void => {
    const w = window.innerWidth;
    const h = window.innerHeight;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h, false);
  };

  private tick = (): void => {
    const elapsed = this.clock.getElapsedTime();
    this.ring.draw(performance.now());
    this.cabinet.updateTexture();
    this.fly.update(this.pose, elapsed);
    this.renderer.render(this.scene, this.camera);
  };
}
