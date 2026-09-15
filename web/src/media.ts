/** Audio clock + optional PV/bg helpers for chart packs. */

export class MediaPlayer {
  readonly audio = new Audio();
  readonly video = document.createElement("video");
  private started = false;
  private ended = false;

  constructor() {
    this.audio.preload = "auto";
    this.audio.loop = false;
    this.video.preload = "auto";
    this.video.muted = true;
    this.video.playsInline = true;
    this.video.loop = false;

    this.audio.addEventListener("ended", () => {
      this.ended = true;
    });
    this.video.addEventListener("ended", () => {
      this.video.pause();
    });
  }

  setTrack(url: string | null): void {
    this.pauseAtEnd();
    if (!url) {
      this.audio.removeAttribute("src");
      this.audio.load();
      return;
    }
    this.audio.src = url;
    this.audio.load();
  }

  setPv(url: string | null): void {
    this.video.pause();
    if (!url) {
      this.video.removeAttribute("src");
      this.video.load();
      return;
    }
    this.video.src = url;
    this.video.load();
  }

  /** Call from a user gesture (Play click) so autoplay policies allow audio. */
  async start(): Promise<void> {
    this.ended = false;
    this.started = true;
    this.audio.currentTime = 0;
    this.video.currentTime = 0;
    const plays: Promise<void>[] = [];
    if (this.audio.src) {
      plays.push(
        this.audio.play().then(
          () => undefined,
          () => undefined,
        ),
      );
    }
    if (this.video.src) {
      plays.push(
        this.video.play().then(
          () => undefined,
          () => undefined,
        ),
      );
    }
    await Promise.all(plays);
  }

  /** Pause at the current frame; do not rewind or restart. */
  pauseAtEnd(): void {
    this.started = false;
    this.ended = true;
    this.audio.pause();
    this.video.pause();
  }

  stop(): void {
    this.started = false;
    this.ended = false;
    this.audio.pause();
    this.video.pause();
    try {
      this.audio.currentTime = 0;
      this.video.currentTime = 0;
    } catch {
      // ignore seek before metadata
    }
  }

  /** Keep media near simulation time t (seconds). */
  sync(t: number): void {
    if (!this.started || this.ended) return;
    if (this.audio.src && !this.audio.paused) {
      const drift = Math.abs(this.audio.currentTime - t);
      if (drift > 0.08) {
        this.audio.currentTime = Math.max(0, t);
      }
    } else if (this.audio.src && this.audio.paused && t > 0.05) {
      void this.audio.play().catch(() => undefined);
    }
    if (this.video.src) {
      if (this.video.paused && t > 0.05 && t < (this.video.duration || Infinity) - 0.05) {
        void this.video.play().catch(() => undefined);
      }
      if (!this.video.paused) {
        const vDrift = Math.abs(this.video.currentTime - t);
        if (vDrift > 0.12) {
          this.video.currentTime = Math.max(0, t);
        }
      }
    }
  }

  get hasVideoFrame(): boolean {
    return Boolean(this.video.src) && this.video.readyState >= 2;
  }
}
