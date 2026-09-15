import type { Drive, Score } from "./protocol";
import type { ConnectionState } from "./ws";

const EMPTY_SCORE: Score = {
  combo: 0,
  perfect: 0,
  great: 0,
  good: 0,
  miss: 0,
  accuracy: 0,
};

const EMPTY_DRIVE: Drive = {
  loomL: 0,
  loomR: 0,
  chaseL: 0,
  chaseR: 0,
  threatL: 0,
  threatR: 0,
};

function pct(v: number): string {
  return `${Math.round(Math.max(0, Math.min(1, v)) * 100)}%`;
}

export class Hud {
  private root: HTMLElement;
  private titleEl: HTMLElement;
  private artistEl: HTMLElement;
  private statusEl: HTMLElement;
  private comboEl: HTMLElement;
  private accuracyEl: HTMLElement;
  private perfectEl: HTMLElement;
  private greatEl: HTMLElement;
  private goodEl: HTMLElement;
  private missEl: HTMLElement;
  private fills: Record<keyof Drive, HTMLElement>;

  constructor(container: HTMLElement) {
    container.innerHTML = `
      <div class="hud-top">
        <div class="hud-title-block">
          <div class="hud-brand">fly-rg</div>
          <div class="hud-title" data-title>Waiting for chart</div>
          <div class="hud-artist" data-artist></div>
        </div>
        <div class="hud-status" data-status data-state="connecting">connecting</div>
      </div>
      <div class="hud-center">
        <div class="hud-score">
          <div class="hud-combo"><span>COMBO</span><b data-combo>0</b></div>
          <div class="hud-accuracy" data-accuracy>0.0% ACC</div>
          <div class="hud-judgments">
            <div>PERFECT <b data-perfect>0</b></div>
            <div>GREAT <b data-great>0</b></div>
            <div>GOOD <b data-good>0</b></div>
            <div>MISS <b data-miss>0</b></div>
          </div>
        </div>
      </div>
      <div class="hud-bottom">
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
      </div>
    `;

    this.root = container;
    this.titleEl = this.must("[data-title]");
    this.artistEl = this.must("[data-artist]");
    this.statusEl = this.must("[data-status]");
    this.comboEl = this.must("[data-combo]");
    this.accuracyEl = this.must("[data-accuracy]");
    this.perfectEl = this.must("[data-perfect]");
    this.greatEl = this.must("[data-great]");
    this.goodEl = this.must("[data-good]");
    this.missEl = this.must("[data-miss]");

    this.fills = {
      loomL: this.must("[data-loomL]"),
      loomR: this.must("[data-loomR]"),
      chaseL: this.must("[data-chaseL]"),
      chaseR: this.must("[data-chaseR]"),
      threatL: this.must("[data-threatL]"),
      threatR: this.must("[data-threatR]"),
    };

    this.setScore(EMPTY_SCORE);
    this.setDrive(EMPTY_DRIVE);
  }

  setConnection(state: ConnectionState): void {
    this.statusEl.dataset.state = state;
    this.statusEl.textContent = state;
  }

  setChart(title: string, artist: string): void {
    this.titleEl.textContent = title || "Untitled";
    this.artistEl.textContent = artist || "";
  }

  setScore(score: Score): void {
    this.comboEl.textContent = String(score.combo);
    this.accuracyEl.textContent = `${(score.accuracy * 100).toFixed(1)}% ACC`;
    this.perfectEl.textContent = String(score.perfect);
    this.greatEl.textContent = String(score.great);
    this.goodEl.textContent = String(score.good);
    this.missEl.textContent = String(score.miss);
  }

  setDrive(drive: Drive): void {
    (Object.keys(this.fills) as Array<keyof Drive>).forEach((key) => {
      this.fills[key].style.width = pct(drive[key]);
    });
  }

  private must(selector: string): HTMLElement {
    const el = this.root.querySelector(selector);
    if (!(el instanceof HTMLElement)) {
      throw new Error(`HUD missing ${selector}`);
    }
    return el;
  }
}
