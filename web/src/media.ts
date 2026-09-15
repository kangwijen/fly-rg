/** Audio clock + optional PV/bg helpers for chart packs. */

export class MediaPlayer {
  readonly audio = new Audio();
  readonly video = document.createElement("video");
  private started = false;

  constructor() {
    this.audio.preload = "auto";
    this.video.preload = "auto";
    this.video.muted = true;
    this.video.playsInline = true;
    this.video.loop = false;
  }

  setTrack(url: string | null): void {
    this.stop();
    if (!url) {
      this.audio.removeAttribute("src");
      return;
    }
    this.audio.src = url;
    this.audio.load();
  }

  setPv(url: string | null): void {
    this.video.pause();
    if (!url) {
      this.video.removeAttribute("src");
      return;
    }
    this.video.src = url;
    this.video.load();
  }

  async start(): Promise<void> {
    this.started = true;
    this.audio.currentTime = 0;
    this.video.currentTime = 0;
    try {
      await this.audio.play();
    } catch {
      // Autoplay may require a prior user gesture; upload click counts.
    }
    if (this.video.src) {
      try {
        await this.video.play();
      } catch {
        // ignore
      }
    }
  }

  stop(): void {
    this.started = false;
    this.audio.pause();
    this.video.pause();
    this.audio.currentTime = 0;
    this.video.currentTime = 0;
  }

  /** Keep media near simulation time t (seconds). */
  sync(t: number): void {
    if (!this.started) return;
    const drift = Math.abs(this.audio.currentTime - t);
    if (drift > 0.08) {
      this.audio.currentTime = Math.max(0, t);
    }
    if (this.video.src && !this.video.paused) {
      const vDrift = Math.abs(this.video.currentTime - t);
      if (vDrift > 0.12) {
        this.video.currentTime = Math.max(0, t);
      }
    }
  }
}
