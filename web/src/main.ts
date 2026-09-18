import { BrainView } from "./brain";
import { revokeChartPack, unpackChartZip, type ChartPack } from "./chartpack";
import { Hud } from "./hud";
import { MediaPlayer } from "./media";
import type { ServerMessage } from "./protocol";
import { buttonToSensor } from "./sensors";
import { ArcadeScene } from "./scene";
import { GameSocket } from "./ws";

function withSkipWarning(base: string, skipped: number | undefined): string {
  if (!skipped) return base;
  const noun = skipped === 1 ? "note" : "notes";
  return `${base} (${skipped} ${noun} skipped)`;
}

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
  let stoppedByUser = false;

  const ring = scene.ring;

  const applyBackground = (): void => {
    if (media.hasVideoFrame) {
      ring.setBackground(media.video);
      scene.cabinet.setVideo(media.video);
    } else if (bgImage && bgImage.complete) {
      scene.cabinet.setVideo(null);
      ring.setBackground(bgImage);
    } else {
      scene.cabinet.setVideo(null);
      ring.setBackground(null);
    }
  };

  const onMessage = (msg: ServerMessage): void => {
    switch (msg.type) {
      case "hello":
        break;
      case "ready":
        playing = false;
        if (stoppedByUser) {
          media.stop();
          hud.resetPlayUi();
        } else {
          hud.setReady(
            withSkipWarning(
              msg.message || "ready · upload a Majdata zip",
              msg.warnings,
            ),
          );
          media.pauseAtEnd();
        }
        stoppedByUser = false;
        break;
      case "levels":
        hud.setLevels(msg.levels);
        hud.setPackHint("pick a difficulty, then Play");
        break;
      case "error":
        hud.setError(withSkipWarning(msg.message, msg.warnings));
        playing = false;
        media.pauseAtEnd();
        hud.setPlaying(false);
        break;
      case "brain_layout":
        brain.setLayout(msg);
        neuronCount = msg.neurons;
        hud.setBrainMeta(neuronCount, 0);
        break;
      case "chart":
        hud.setChart(msg.title, msg.artist);
        if (msg.warnings) {
          hud.setPackHint(withSkipWarning("playing", msg.warnings));
        }
        playing = true;
        hud.setPlaying(true);
        if (msg.active) {
          ring.setActive(msg.active);
        }
        if (msg.active_sensors) {
          ring.setActiveSensors(msg.active_sensors);
        }
        applyBackground();
        break;
      case "state": {
        if (stoppedByUser) break;
        const aimSensor =
          msg.aim_sensor ??
          (msg.aim_button != null ? buttonToSensor(msg.aim_button) : null);
        const tapSensor =
          msg.tap_sensor ??
          (msg.tap_button != null ? buttonToSensor(msg.tap_button) : null);

        ring.setActive(msg.active);
        ring.setAimSensor(aimSensor, msg.tap, tapSensor);
        if (msg.active_sensors) {
          ring.setActiveSensors(msg.active_sensors);
        }

        scene.setHands(msg.hand_l, msg.hand_r);
        ring.setHandTips(
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
        if (playing) {
          if (!media.started) {
            void media.start().then(() => media.sync(msg.t));
          } else {
            media.sync(msg.t);
          }
        }
        applyBackground();
        break;
      }
      case "hit": {
        const target = msg.sensor ?? msg.button;
        if (target != null) ring.flashHit(target, msg.judgment);
        hud.flashJudgment(msg.judgment, msg.timing);
        break;
      }
      case "end":
        hud.setScore(msg.score);
        playing = false;
        media.pauseAtEnd();
        hud.setPlaying(false);
        hud.setPackHint("finished · upload another zip or Play again");
        break;
      case "resources":
        hud.setResources(msg);
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
    onState: (state) => {
      hud.setConnection(state);
      if (state === "closed" || state === "error") {
        playing = false;
        media.pauseAtEnd();
        hud.setPlaying(false);
      }
    },
  });

  hud.onUpload(async (file) => {
    const previous = pack;
    try {
      hud.setPackHint(`unpacking ${file.name}...`);
      pack = null;
      const next = await unpackChartZip(file);
      revokeChartPack(previous);
      pack = next;
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
      pack = previous;
      hud.setError(err instanceof Error ? err.message : String(err));
    }
  });

  hud.onPlayClick((difficulty) => {
    if (!pack) {
      hud.setError("upload a zip first");
      return;
    }
    // load_chart already stop_play then starts from t=0; do not send stop
    // (that would emit ready and pause the just-unlocked track).
    // Unlock autoplay inside the click gesture; real start waits for state t.
    stoppedByUser = false;
    void media.unlock();
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

  hud.onStopClick(() => {
    stoppedByUser = true;
    socket.send({ type: "stop" });
    media.stop();
    playing = false;
    ring.setActive([]);
    scene.setHands(null, null);
    ring.setHandTips(null, null);
    hud.resetPlayUi();
    hud.setPlaying(false);
  });

  scene.start(() => {
    brain.draw();
  });
  socket.connect();
}

boot();
