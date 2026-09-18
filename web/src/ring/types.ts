export interface Pt {
  x: number;
  y: number;
}

export interface Flash {
  sensor: string;
  color: string;
  until: number;
}

export interface HighlightStyle {
  fill: string;
  stroke: string;
  glow: number;
}

export interface HandSample {
  x: number;
  y: number;
  strike: number;
}
