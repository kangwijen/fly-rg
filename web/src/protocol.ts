export type Judgment = "critical" | "perfect" | "great" | "good" | "miss";

export interface Score {
  combo: number;
  critical: number;
  perfect: number;
  great: number;
  good: number;
  miss: number;
  mine?: number;
  accuracy: number;
  achievement: number;
  dx_score: number;
  dx_max: number;
}

export interface SlideInfo {
  shape?: string;
  end_sensor?: string;
  path?: string[];
  end_t?: number;
  wait_t?: number;
  mid?: number | null;
}

export interface ChartNote {
  t: number;
  button: number | null;
  type: string;
  end?: number | null;
  sensor?: string;
  slide?: SlideInfo | null;
  is_break?: boolean;
  is_ex?: boolean;
  is_mine?: boolean;
  is_hanabi?: boolean;
  is_star?: boolean;
  is_each?: boolean;
  head_style?: string;
}

export interface ActiveNote {
  t: number;
  button: number | null;
  progress: number;
  sensor?: string;
  type?: string;
  end?: number | null;
  hold_phase?: "approach" | "sustain";
  path?: string[];
  slide?: SlideInfo | null;
  is_break?: boolean;
  is_ex?: boolean;
  is_mine?: boolean;
  is_hanabi?: boolean;
  is_star?: boolean;
  is_each?: boolean;
  head_style?: string;
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
  strike_l?: number;
  strike_r?: number;
  omega_l?: number;
  omega_r?: number;
  reach_l?: number;
  reach_r?: number;
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
  active?: ActiveNote[];
  active_sensors?: string[];
  warnings?: number;
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
  hand_l_sensor?: string | null;
  hand_r_sensor?: string | null;
  /** Unit disk, x right, y up, origin C. Tip target; not a pad id. */
  hand_l?: [number, number] | null;
  hand_r?: [number, number] | null;
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
  timing?: "fast" | "late" | null;
}

export interface EndMessage {
  type: "end";
  score: Score;
}

export interface ReadyMessage {
  type: "ready";
  message?: string;
  warnings?: number;
}

export interface LevelsMessage {
  type: "levels";
  levels: Array<{ difficulty: number; level: string }>;
}

export interface ErrorMessage {
  type: "error";
  message: string;
  warnings?: number;
}

export interface Resources {
  cpu_pct: number;
  sys_cpu_pct: number | null;
  rss_mb: number;
  ram_used_mb: number | null;
  ram_total_mb: number | null;
  gpu_pct: number | null;
  vram_used_mb: number | null;
  vram_total_mb: number | null;
  gpu_name: string | null;
}

export interface ResourcesMessage extends Resources {
  type: "resources";
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
  | ErrorMessage
  | ResourcesMessage;

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
    type === "error" ||
    type === "resources"
  );
}
