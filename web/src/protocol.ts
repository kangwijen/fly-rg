export type Judgment = "perfect" | "great" | "good" | "miss";

export interface Score {
  combo: number;
  perfect: number;
  great: number;
  good: number;
  miss: number;
  accuracy: number;
}

export interface SlideInfo {
  shape?: string;
  end_sensor?: string;
  path?: string[];
  end_t?: number;
}

export interface ChartNote {
  t: number;
  button: number;
  type: string;
  end?: number | null;
  sensor?: string;
  slide?: SlideInfo | null;
}

export interface ActiveNote {
  t: number;
  button: number;
  progress: number;
  sensor?: string;
  type?: string;
  path?: string[];
  slide?: SlideInfo | null;
}

export interface Drive {
  loomL: number;
  loomR: number;
  chaseL: number;
  chaseR: number;
  threatL: number;
  threatR: number;
}

export interface Pose {
  aim: number;
  strike: number;
}

export interface HelloMessage {
  type: "hello";
  version: number;
}

export interface ChartMessage {
  type: "chart";
  title: string;
  artist: string;
  notes: ChartNote[];
}

export interface BrainLayoutMessage {
  type: "brain_layout";
  neurons: number;
  x: number[];
  y: number[];
  groups: Record<string, number[]>;
  labels: Record<string, string>;
}

export interface StateMessage {
  type: "state";
  t: number;
  aim_button: number | null;
  tap: boolean;
  tap_button: number | null;
  aim_sensor?: string | null;
  tap_sensor?: string | null;
  score: Score;
  active: ActiveNote[];
  active_sensors?: string[];
  drive: Drive;
  pose: Pose;
  spikes?: number[];
  spike_total?: number;
}

export interface HitMessage {
  type: "hit";
  button: number | null;
  judgment: Judgment;
  sensor?: string | null;
  t: number;
}

export interface EndMessage {
  type: "end";
  score: Score;
}

export interface ReadyMessage {
  type: "ready";
  message?: string;
}

export interface LevelsMessage {
  type: "levels";
  levels: Array<{ difficulty: number; level: string }>;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export type ServerMessage =
  | HelloMessage
  | ChartMessage
  | BrainLayoutMessage
  | StateMessage
  | HitMessage
  | EndMessage
  | ReadyMessage
  | LevelsMessage
  | ErrorMessage;

export type ClientMessage =
  | { type: "inspect_chart"; maidata: string }
  | { type: "load_chart"; maidata: string; difficulty?: number | null }
  | { type: "stop" };

export function isServerMessage(value: unknown): value is ServerMessage {
  if (!value || typeof value !== "object") return false;
  const type = (value as { type?: unknown }).type;
  return (
    type === "hello" ||
    type === "chart" ||
    type === "brain_layout" ||
    type === "state" ||
    type === "hit" ||
    type === "end" ||
    type === "ready" ||
    type === "levels" ||
    type === "error"
  );
}
