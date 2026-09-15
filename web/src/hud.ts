import type { Drive, Judgment, Score } from "./protocol";
import type { ConnectionState } from "./ws";

const EMPTY_SCORE: Score = {
  combo: 0,
  critical: 0,
  perfect: 0,
  great: 0,
  good: 0,
  miss: 0,
  accuracy: 0,
  achievement: 0,
  dx_score: 0,
  dx_max: 0,
};

const JUDGMENT_FLASH_MS = 700;

const EMPTY_DRIVE: Drive = {
  loomL: 0,
  loomR: 0,
  chaseL: 0,
  chaseR: 0,
  threatL: 0,
  threatR: 0,
};

export type LevelInfo = { difficulty: number; level: string };

function pct(v: number): string {
  return `${Math.round(Math.max(0, Math.min(1, v)) * 100)}%`;
}

function formatAchievement(ratio: number): string {
  const pctValue = Math.floor(ratio * 1_000_000 + 1e-9) / 10_000;
  return `${pctValue.toFixed(4)}%`;
}

function judgmentWord(judgment: Judgment): string {
  switch (judgment) {
    case "critical":
      return "CRITICAL PERFECT";
    case "perfect":
      return "PERFECT";
    case "great":
      return "GREAT";
    case "good":
      return "GOOD";
    case "miss":
      return "MISS";
    default: {
      const _exhaustive: never = judgment;
      return _exhaustive;
    }
  }
}

function judgmentPopupText(
  judgment: Judgment,
  timing?: "fast" | "late" | null,
): string {
  if (judgment === "critical" || judgment === "miss") {
    return judgmentWord(judgment);
  }
  const word = judgmentWord(judgment);
  if (timing === "fast") return `${word} FAST`;
  if (timing === "late") return `${word} LATE`;
  if (timing == null) return word;
  const _exhaustive: never = timing;
  return _exhaustive;
}

export class Hud {
  private gameRoot: HTMLElement;
  private neuralRoot: HTMLElement;
  private titleEl: HTMLElement;
  private artistEl: HTMLElement;
  private statusEl: HTMLElement;
  private comboEl: HTMLElement;
  private scoreEl: HTMLElement;
  private accuracyEl: HTMLElement;
  private criticalEl: HTMLElement;
  private perfectEl: HTMLElement;
  private greatEl: HTMLElement;
  private goodEl: HTMLElement;
  private missEl: HTMLElement;
  private judgmentFlashEl: HTMLElement;
  private judgmentTimer = 0;
  private hintEl: HTMLElement;
  private metaEl: HTMLElement;
  private brainHost: HTMLElement;
  private levelSelect: HTMLSelectElement;
  private fileInput: HTMLInputElement;
  private playBtn: HTMLButtonElement;
  private fills: Record<keyof Drive, HTMLElement>;
  private onZipSelected: ((file: File) => void) | null = null;
  private onPlay: ((difficulty: number | null) => void) | null = null;

  constructor(gameOverlay: HTMLElement, neuralPane: HTMLElement) {
    gameOverlay.innerHTML = `
      <div class="hud-judgment-flash" data-judgment-flash hidden></div>
      <div class="hud-title-block">
        <div class="hud-brand">fly-rg</div>
        <div class="hud-title" data-title>Upload a chart zip</div>
        <div class="hud-artist" data-artist></div>
        <div class="hud-hint" data-hint>Majdata pack: maidata.txt + track.ogg/mp3 + bg.png/jpg (+ pv.mp4). Drag to orbit.</div>
        <div class="hud-upload">
          <label class="upload-btn">
            Choose zip
            <input type="file" accept=".zip,application/zip" data-zip hidden />
          </label>
          <select data-level disabled>
            <option value="">difficulty</option>
          </select>
          <button type="button" data-play disabled>Play</button>
        </div>
      </div>
      <div class="hud-watermark">@kangwijen</div>
    `;

    neuralPane.innerHTML = `
      <div class="neural-header">
        <div>
          <div class="neural-title">Neural Activity</div>
          <div class="neural-meta" data-meta>waiting for layout</div>
        </div>
        <div class="hud-status" data-status data-state="connecting">connecting</div>
      </div>
      <div class="brain-host" data-brain></div>
      <div class="brain-legend">
        <span><i class="lg loom"></i>loom</span>
        <span><i class="lg threat"></i>threat</span>
        <span><i class="lg chase"></i>chase</span>
        <span><i class="lg cmd"></i>command</span>
        <span><i class="lg spike"></i>spike</span>
      </div>
      <div class="neural-score">
        <div class="hud-combo"><span>COMBO</span><b data-combo>0</b></div>
        <div class="hud-score"><span>SCORE</span><b data-score>0.0000%</b></div>
        <div class="hud-accuracy" data-accuracy>0.0% ACC</div>
        <div class="hud-judgments">
          <div class="judge-critical">CRITICAL <b data-critical>0</b></div>
          <div>PERFECT <b data-perfect>0</b></div>
          <div>GREAT <b data-great>0</b></div>
          <div>GOOD <b data-good>0</b></div>
          <div>MISS <b data-miss>0</b></div>
        </div>
      </div>
      <div class="hud-drives">
        <div class="drive-group">
          <div class="drive-label">Loom</div>
          <div class="drive-row"><span>L</span><div class="drive-bar"><div class="drive-fill" data-loomL></div></div></div>
          <div class="drive-row"><span>R</span><div class="drive-bar"><div class="drive-fill" data-loomR></div></div></div>
        </div>
        <div class="drive-group">
          <div class="drive-label">Chase</div>
          <div class="drive-row"><span>L</span><div class="drive-bar"><div class="drive-fill" data-chaseL></div></div></div>
          <div class="drive-row"><span>R</span><div class="drive-bar"><div class="drive-fill" data-chaseR></div></div></div>
        </div>
        <div class="drive-group">
          <div class="drive-label">Threat</div>
          <div class="drive-row"><span>L</span><div class="drive-bar"><div class="drive-fill threat" data-threatL></div></div></div>
          <div class="drive-row"><span>R</span><div class="drive-bar"><div class="drive-fill threat" data-threatR></div></div></div>
        </div>
      </div>
    `;

    this.gameRoot = gameOverlay;
    this.neuralRoot = neuralPane;
    this.titleEl = this.mustGame("[data-title]");
    this.artistEl = this.mustGame("[data-artist]");
    this.hintEl = this.mustGame("[data-hint]");
    this.statusEl = this.mustNeural("[data-status]");
    this.metaEl = this.mustNeural("[data-meta]");
    this.comboEl = this.mustNeural("[data-combo]");
    this.scoreEl = this.mustNeural("[data-score]");
    this.accuracyEl = this.mustNeural("[data-accuracy]");
    this.criticalEl = this.mustNeural("[data-critical]");
    this.perfectEl = this.mustNeural("[data-perfect]");
    this.judgmentFlashEl = this.mustGame("[data-judgment-flash]");
    this.greatEl = this.mustNeural("[data-great]");
    this.goodEl = this.mustNeural("[data-good]");
    this.missEl = this.mustNeural("[data-miss]");
    this.brainHost = this.mustNeural("[data-brain]");
    this.levelSelect = this.mustGame("[data-level]") as HTMLSelectElement;
    this.fileInput = this.mustGame("[data-zip]") as HTMLInputElement;
    this.playBtn = this.mustGame("[data-play]") as HTMLButtonElement;

    this.fills = {
      loomL: this.mustNeural("[data-loomL]"),
      loomR: this.mustNeural("[data-loomR]"),
      chaseL: this.mustNeural("[data-chaseL]"),
      chaseR: this.mustNeural("[data-chaseR]"),
      threatL: this.mustNeural("[data-threatL]"),
      threatR: this.mustNeural("[data-threatR]"),
    };

    this.fileInput.addEventListener("change", () => {
      const file = this.fileInput.files?.[0];
      if (file && this.onZipSelected) this.onZipSelected(file);
    });
    this.playBtn.addEventListener("click", () => {
      const raw = this.levelSelect.value;
      const difficulty = raw === "" ? null : Number(raw);
      this.onPlay?.(difficulty);
    });

    this.setScore(EMPTY_SCORE);
    this.setDrive(EMPTY_DRIVE);
  }

  onUpload(handler: (file: File) => void): void {
    this.onZipSelected = handler;
  }

  onPlayClick(handler: (difficulty: number | null) => void): void {
    this.onPlay = handler;
  }

  mountBrain(canvas: HTMLCanvasElement): void {
    this.brainHost.replaceChildren(canvas);
  }

  setConnection(state: ConnectionState): void {
    this.statusEl.dataset.state = state;
    this.statusEl.textContent = state;
    if (state === "open") {
      this.hintEl.textContent =
        "connected · upload a Majdata zip · drag canvas to orbit";
    } else if (state === "closed" || state === "error") {
      this.hintEl.textContent =
        "Server offline. Run: python -m fly_rg.play --mock";
    } else {
      this.hintEl.textContent = "connecting to play server...";
    }
  }

  setLevels(levels: LevelInfo[]): void {
    this.levelSelect.innerHTML = "";
    if (!levels.length) {
      this.levelSelect.disabled = true;
      this.playBtn.disabled = true;
      this.levelSelect.innerHTML = `<option value="">no levels</option>`;
      return;
    }
    for (const lv of levels) {
      const opt = document.createElement("option");
      opt.value = String(lv.difficulty);
      opt.textContent = lv.level
        ? `inote_${lv.difficulty} (lv ${lv.level})`
        : `inote_${lv.difficulty}`;
      this.levelSelect.appendChild(opt);
    }
    // Prefer highest difficulty as default (often Master).
    this.levelSelect.value = String(levels[levels.length - 1].difficulty);
    this.levelSelect.disabled = false;
    this.playBtn.disabled = false;
  }

  setPackHint(text: string): void {
    this.hintEl.textContent = text;
  }

  setChart(title: string, artist: string): void {
    this.titleEl.textContent = title || "Untitled";
    this.artistEl.textContent = artist || "";
    this.hintEl.textContent = "playing";
  }

  setReady(message: string): void {
    this.hintEl.textContent = message;
  }

  setError(message: string): void {
    this.hintEl.textContent = message;
  }

  setBrainMeta(neurons: number, spikeTotal: number): void {
    if (neurons > 0) {
      this.metaEl.textContent = `${neurons} neurons · ${spikeTotal} spikes/frame`;
    } else {
      this.metaEl.textContent = `${spikeTotal} spikes/frame`;
    }
  }

  setScore(score: Score): void {
    this.comboEl.textContent = String(score.combo);
    this.scoreEl.textContent = formatAchievement(score.achievement ?? 0);
    const acc = score.accuracy ?? 0;
    const dxScore = score.dx_score ?? 0;
    const dxMax = score.dx_max ?? 0;
    this.accuracyEl.textContent =
      dxMax > 0
        ? `${(acc * 100).toFixed(1)}% ACC  ${dxScore}/${dxMax}`
        : `${(acc * 100).toFixed(1)}% ACC`;
    this.criticalEl.textContent = String(score.critical ?? 0);
    this.perfectEl.textContent = String(score.perfect);
    this.greatEl.textContent = String(score.great);
    this.goodEl.textContent = String(score.good);
    this.missEl.textContent = String(score.miss);
  }

  flashJudgment(judgment: Judgment, timing?: "fast" | "late" | null): void {
    this.judgmentFlashEl.textContent = judgmentPopupText(judgment, timing);
    this.judgmentFlashEl.dataset.judgment = judgment;
    this.judgmentFlashEl.hidden = false;
    this.judgmentFlashEl.classList.remove("is-on");
    void this.judgmentFlashEl.offsetWidth;
    this.judgmentFlashEl.classList.add("is-on");
    window.clearTimeout(this.judgmentTimer);
    this.judgmentTimer = window.setTimeout(() => {
      this.judgmentFlashEl.classList.remove("is-on");
      this.judgmentFlashEl.hidden = true;
    }, JUDGMENT_FLASH_MS);
  }

  setDrive(drive: Drive): void {
    (Object.keys(this.fills) as Array<keyof Drive>).forEach((key) => {
      this.fills[key].style.width = pct(drive[key]);
    });
  }

  private mustGame(selector: string): HTMLElement {
    const el = this.gameRoot.querySelector(selector);
    if (!(el instanceof HTMLElement)) {
      throw new Error(`Game overlay missing ${selector}`);
    }
    return el;
  }

  private mustNeural(selector: string): HTMLElement {
    const el = this.neuralRoot.querySelector(selector);
    if (!(el instanceof HTMLElement)) {
      throw new Error(`Neural pane missing ${selector}`);
    }
    return el;
  }
}
