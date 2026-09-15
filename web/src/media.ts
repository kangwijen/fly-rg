/** Audio clock + optional PV/bg helpers for chart packs. */

export class MediaPlayer {
  readonly audio = new Audio();
  readonly video = document.createElement("video");
  private _started = false;
  private ended = false;
  /** When true, the next sync() may seek to t in either direction. */
  private initialSyncPending = false;

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

  get started(): boolean {
    return this._started;
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

  /**
   * Satisfy autoplay policy on Play click without advancing the song clock.
   * Leaves the track paused at t=0 until start().
   */
  async unlock(): Promise<void> {
    this._started = false;
    this.ended = false;
    this.initialSyncPending = false;

    const plays: Promise<void>[] = [];
    if (this.audio.src) {
      const wasMuted = this.audio.muted;
      this.audio.muted = true;
      this.audio.currentTime = 0;
      plays.push(
        this.audio
          .play()
          .then(() => {
            this.audio.pause();
            this.audio.currentTime = 0;
            this.audio.muted = wasMuted;
          })
          .catch(() => {
            this.audio.muted = wasMuted;
          }),
      );
    }
    if (this.video.src) {
      this.video.currentTime = 0;
      plays.push(
        this.video.play().then(
          () => {
            this.video.pause();
            this.video.currentTime = 0;
          },
          () => undefined,
        ),
      );
    }
    await Promise.all(plays);
  }

  /** Begin playback from t=0 when the simulation is ready. */
  async start(): Promise<void> {
    this.ended = false;
    this._started = true;
    this.initialSyncPending = true;
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
    this._started = false;
    this.ended = true;
    this.initialSyncPending = false;
    this.audio.pause();
    this.video.pause();
  }

  stop(): void {
    this._started = false;
    this.ended = false;
    this.initialSyncPending = false;
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
    if (!this._started || this.ended) return;

    if (this.initialSyncPending) {
      this.initialSyncPending = false;
      const seekT = Math.max(0, t);
      if (this.audio.src) {
        try {
          this.audio.currentTime = seekT;
        } catch {
          // ignore seek before metadata
        }
        if (this.audio.paused && t > 0.05) {
          void this.audio.play().catch(() => undefined);
        }
      }
      if (this.video.src) {
        try {
          this.video.currentTime = seekT;
        } catch {
          // ignore seek before metadata
        }
        if (this.video.paused && t > 0.05 && t < (this.video.duration || Infinity) - 0.05) {
          void this.video.play().catch(() => undefined);
        }
      }
      return;
    }

    // After the first lock, let media run at 1x. Seeking here used to jump the
    // song whenever the sim caught up in bursts.
    if (this.audio.src && this.audio.paused && t > 0.05) {
      void this.audio.play().catch(() => undefined);
    }
    if (
      this.video.src &&
      this.video.paused &&
      t > 0.05 &&
      t < (this.video.duration || Infinity) - 0.05
    ) {
      void this.video.play().catch(() => undefined);
    }
  }

  get hasVideoFrame(): boolean {
    return Boolean(this.video.src) && this.video.readyState >= 2;
  }
}
