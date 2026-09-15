import { BrainView } from "./brain";
import { revokeChartPack, unpackChartZip, type ChartPack } from "./chartpack";
import { Hud } from "./hud";
import { MediaPlayer } from "./media";
import type { ServerMessage } from "./protocol";
import { buttonToSensor } from "./sensors";
import { ArcadeScene } from "./scene";
import { GameSocket } from "./ws";

type RingWithSensors = ArcadeScene["ring"] & {
  setAimSensor?: (
    sensor: string | null,
    tap: boolean,
    tapSensor: string | null,
  ) => void;
  setActiveSensors?: (sensors: string[]) => void;
  setBackground?: (source: CanvasImageSource | null) => void;
};

function boot(): void {
  const canvas = document.querySelector<HTMLCanvasElement>("#scene");
  const gamePane = document.querySelector<HTMLElement>("#game-pane");
  const gameOverlay = document.querySelector<HTMLElement>("#game-overlay");
  const neuralPane = document.querySelector<HTMLElement>("#neural-pane");
  if (!canvas || !gamePane || !gameOverlay || !neuralPane) {
    throw new Error("Missing #scene, #game-pane, #game-overlay, or #neural-pane");
  }

  const scene = new ArcadeScene(canvas, gamePane);
  const hud = new Hud(gameOverlay, neuralPane);
  const brain = new BrainView();
  const media = new MediaPlayer();
  hud.mountBrain(brain.canvas);

  let neuronCount = 0;
  let pack: ChartPack | null = null;
  let bgImage: HTMLImageElement | null = null;
  let playing = false;

  const ring = scene.ring as RingWithSensors;

  const applyBackground = (): void => {
    if (!ring.setBackground) return;
    if (media.hasVideoFrame) {
      ring.setBackground(media.video);
    } else if (bgImage && bgImage.complete) {
      ring.setBackground(bgImage);
    } else {
      ring.setBackground(null);
    }
  };

  const onMessage = (msg: ServerMessage): void => {
    switch (msg.type) {
      case "hello":
        break;
      case "ready":
        hud.setReady(msg.message || "ready · upload a Majdata zip");
        playing = false;
        media.pauseAtEnd();
        break;
      case "levels":
        hud.setLevels(msg.levels);
        hud.setPackHint("pick a difficulty, then Play");
        break;
      case "error":
        hud.setError(msg.message);
        playing = false;
        media.pauseAtEnd();
        break;
      case "brain_layout":
        brain.setLayout(msg);
        neuronCount = msg.neurons;
        hud.setBrainMeta(neuronCount, 0);
        break;
      case "chart":
        hud.setChart(msg.title, msg.artist);
        playing = true;
        applyBackground();
        break;
      case "state": {
        const aimSensor =
          msg.aim_sensor ??
          (msg.aim_button != null ? buttonToSensor(msg.aim_button) : null);
        const tapSensor =
          msg.tap_sensor ??
          (msg.tap_button != null ? buttonToSensor(msg.tap_button) : null);

        scene.ring.setActive(msg.active);
        scene.setActiveNotes(msg.active);
        if (typeof ring.setAimSensor === "function") {
          ring.setAimSensor(aimSensor, msg.tap, tapSensor);
        } else {
          scene.ring.setAim(msg.aim_button, msg.tap, msg.tap_button);
        }
        if (msg.active_sensors && typeof ring.setActiveSensors === "function") {
          ring.setActiveSensors(msg.active_sensors);
        }

        if (aimSensor) {
          scene.setAimSensor(aimSensor);
        } else {
          scene.setAimButton(msg.aim_button);
        }
        scene.setHands(msg.hand_l, msg.hand_r);
        scene.ring.setHandTips(
          msg.hand_l,
          msg.hand_r,
          msg.pose.strike_l ?? msg.pose.strike,
          msg.pose.strike_r ?? msg.pose.strike,
        );

        scene.setPose(msg.pose);
        hud.setScore(msg.score);
        hud.setDrive(msg.drive);
        brain.setState(msg.spikes ?? [], msg.spike_total ?? 0, msg.drive, msg.pose);
        hud.setBrainMeta(neuronCount, msg.spike_total ?? 0);
        if (playing) media.sync(msg.t);
        applyBackground();
        break;
      }
      case "hit": {
        const target = msg.sensor ?? msg.button;
        if (target != null) scene.ring.flashHit(target, msg.judgment);
        hud.flashJudgment(msg.judgment, msg.timing);
        break;
      }
      case "end":
        hud.setScore(msg.score);
        playing = false;
        media.pauseAtEnd();
        hud.setPackHint("finished · upload another zip or Play again");
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

  hud.onUpload(async (file) => {
    try {
      hud.setPackHint(`unpacking ${file.name}...`);
      revokeChartPack(pack);
      pack = await unpackChartZip(file);
      media.setTrack(pack.trackUrl);
      media.setPv(pack.pvUrl);
      bgImage = null;
      if (pack.bgUrl) {
        const img = new Image();
        img.onload = () => {
          bgImage = img;
          applyBackground();
        };
        img.src = pack.bgUrl;
      } else {
        applyBackground();
      }
      const bits = [
        "maidata.txt",
        pack.trackName,
        pack.bgName,
        pack.pvName,
      ].filter(Boolean);
      hud.setPackHint(`loaded ${bits.join(" · ")}`);
      if (!socket.send({ type: "inspect_chart", maidata: pack.maidata })) {
        hud.setError("not connected to play server");
      }
    } catch (err) {
      hud.setError(err instanceof Error ? err.message : String(err));
    }
  });

  hud.onPlayClick((difficulty) => {
    if (!pack) {
      hud.setError("upload a zip first");
      return;
    }
    // Start media inside the click gesture so browsers allow audio.
    void media.start().then(() => applyBackground());
    if (
      !socket.send({
        type: "load_chart",
        maidata: pack.maidata,
        difficulty,
      })
    ) {
      media.pauseAtEnd();
      hud.setError("not connected to play server");
    }
  });

  const drawBrain = (): void => {
    brain.draw();
    requestAnimationFrame(drawBrain);
  };
  drawBrain();

  scene.start();
  socket.connect();
}

boot();
