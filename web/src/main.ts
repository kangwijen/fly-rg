import { Hud } from "./hud";
import type { ServerMessage } from "./protocol";
import { ArcadeScene } from "./scene";
import { GameSocket } from "./ws";

function boot(): void {
  const canvas = document.querySelector<HTMLCanvasElement>("#scene");
  const hudRoot = document.querySelector<HTMLElement>("#hud");
  if (!canvas || !hudRoot) {
    throw new Error("Missing #scene or #hud");
  }

  const scene = new ArcadeScene(canvas);
  const hud = new Hud(hudRoot);

  const onMessage = (msg: ServerMessage): void => {
    switch (msg.type) {
      case "hello":
        break;
      case "chart":
        hud.setChart(msg.title, msg.artist);
        break;
      case "state":
        scene.ring.setActive(msg.active);
        scene.ring.setAim(msg.aim_button, msg.tap, msg.tap_button);
        scene.fly.setAimButton(msg.aim_button);
        scene.setPose(msg.pose);
        hud.setScore(msg.score);
        hud.setDrive(msg.drive);
        break;
      case "hit":
        scene.ring.flashHit(msg.button, msg.judgment);
        break;
      case "end":
        hud.setScore(msg.score);
        break;
      default: {
        const _exhaustive: never = msg;
        void _exhaustive;
        break;
      }
    }
  };

  const socket = new GameSocket({
    onMessage,
    onState: (state) => hud.setConnection(state),
  });

  scene.start();
  socket.connect();
}

boot();
