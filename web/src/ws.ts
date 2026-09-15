import { isServerMessage, type ClientMessage, type ServerMessage } from "./protocol";

export type ConnectionState = "connecting" | "open" | "closed" | "error";

export type WsHandlers = {
  onMessage?: (msg: ServerMessage) => void;
  onState?: (state: ConnectionState) => void;
};

function resolveUrl(explicit?: string): string {
  if (explicit) return explicit;

  const params = new URLSearchParams(window.location.search);
  const override = params.get("ws");
  if (override) return override;

  return "ws://127.0.0.1:8765";
}

export class GameSocket {
  private url: string;
  private handlers: WsHandlers;
  private socket: WebSocket | null = null;
  private closedByUser = false;
  private attempt = 0;
  private reconnectTimer: number | null = null;

  constructor(handlers: WsHandlers = {}, url?: string) {
    this.handlers = handlers;
    this.url = resolveUrl(url);
  }

  connect(): void {
    this.closedByUser = false;
    this.clearReconnect();
    this.setState("connecting");

    const socket = new WebSocket(this.url);
    this.socket = socket;

    socket.addEventListener("open", () => {
      this.attempt = 0;
      this.setState("open");
    });

    socket.addEventListener("message", (event) => {
      try {
        const data = JSON.parse(String(event.data)) as unknown;
        if (!isServerMessage(data)) return;
        this.handlers.onMessage?.(data);
      } catch {
        // ignore malformed frames
      }
    });

    socket.addEventListener("close", () => {
      this.socket = null;
      if (this.closedByUser) {
        this.setState("closed");
        return;
      }
      this.setState("closed");
      this.scheduleReconnect();
    });

    socket.addEventListener("error", () => {
      this.setState("error");
    });
  }

  send(msg: ClientMessage): boolean {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify(msg));
    return true;
  }

  disconnect(): void {
    this.closedByUser = true;
    this.clearReconnect();
    this.socket?.close();
    this.socket = null;
    this.setState("closed");
  }

  private scheduleReconnect(): void {
    this.clearReconnect();
    const delay = Math.min(10_000, 400 * 2 ** this.attempt);
    this.attempt += 1;
    this.reconnectTimer = window.setTimeout(() => this.connect(), delay);
  }

  private clearReconnect(): void {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private setState(state: ConnectionState): void {
    this.handlers.onState?.(state);
  }
}
