import { isServerMessage, type ClientMessage, type ServerMessage } from "./protocol";

export type ConnectionState = "connecting" | "open" | "closed" | "error";

export type WsHandlers = {
  onMessage?: (msg: ServerMessage) => void;
  onState?: (state: ConnectionState) => void;
};

function pageHostname(): string {
  return window.location.hostname.toLowerCase();
}

function isLocalPageHost(hostname: string): boolean {
  const h = hostname.toLowerCase();
  return h === "localhost" || h === "127.0.0.1" || h === "::1" || h === "[::1]";
}

function isAllowedWsHost(hostname: string): boolean {
  const h = hostname.toLowerCase();
  if (isLocalPageHost(h)) return true;
  return h === pageHostname();
}

function defaultWsUrl(): string {
  const host = window.location.hostname;
  if (window.location.protocol === "https:" && !isLocalPageHost(host)) {
    return `wss://${host}:8765`;
  }
  return "ws://127.0.0.1:8765";
}

function normalizeWsUrl(raw: string): string | null {
  let candidate = raw.trim();
  if (!candidate) return null;

  if (!/^wss?:\/\//i.test(candidate)) {
    candidate = `ws://${candidate}`;
  }

  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    console.error(`Invalid WebSocket URL, using default: ${raw}`);
    return null;
  }

  if (parsed.protocol !== "ws:" && parsed.protocol !== "wss:") {
    console.error(`WebSocket URL must use ws: or wss:, using default: ${raw}`);
    return null;
  }

  if (!isAllowedWsHost(parsed.hostname)) {
    console.error(
      `WebSocket host not allow-listed (${parsed.hostname}), using default`,
    );
    return null;
  }

  return parsed.toString();
}

function resolveUrl(explicit?: string): string {
  if (explicit) {
    return normalizeWsUrl(explicit) ?? defaultWsUrl();
  }

  const params = new URLSearchParams(window.location.search);
  const override = params.get("ws");
  if (override) {
    return normalizeWsUrl(override) ?? defaultWsUrl();
  }

  return defaultWsUrl();
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

    let socket: WebSocket;
    try {
      socket = new WebSocket(this.url);
    } catch (err) {
      console.error("WebSocket constructor failed:", err);
      this.setState("error");
      this.scheduleReconnect();
      return;
    }

    this.socket = socket;

    socket.addEventListener("open", () => {
      this.attempt = 0;
      this.setState("open");
    });

    socket.addEventListener("message", (event) => {
      let data: unknown;
      try {
        data = JSON.parse(String(event.data)) as unknown;
      } catch {
        return;
      }
      if (!isServerMessage(data)) return;
      try {
        this.handlers.onMessage?.(data);
      } catch (err) {
        console.error("WebSocket message handler failed:", err);
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
