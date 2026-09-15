export type Judgment = "perfect" | "great" | "good" | "miss";

export interface Score {
  combo: number;
  perfect: number;
  great: number;
  good: number;
  miss: number;
  accuracy: number;
}

export interface ChartNote {
  t: number;
  button: number;
  type: string;
  end?: number;
}

export interface ActiveNote {
  t: number;
  button: number;
  progress: number;
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

export interface StateMessage {
  type: "state";
  t: number;
  aim_button: number | null;
  tap: boolean;
  tap_button: number | null;
  score: Score;
  active: ActiveNote[];
  drive: Drive;
  pose: Pose;
}

export interface HitMessage {
  type: "hit";
  t: number;
  button: number;
  judgment: Judgment;
}

export interface EndMessage {
  type: "end";
  score: Score;
}

export type ServerMessage =
  | HelloMessage
  | ChartMessage
  | StateMessage
  | HitMessage
  | EndMessage;

export function isServerMessage(value: unknown): value is ServerMessage {
  if (!value || typeof value !== "object") return false;
  const type = (value as { type?: unknown }).type;
  return (
    type === "hello" ||
    type === "chart" ||
    type === "state" ||
    type === "hit" ||
    type === "end"
  );
}
