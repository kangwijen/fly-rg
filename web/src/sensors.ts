/** maimai DX touch sensor geometry (Majdata TouchDrop.GetAreaPos). */

export type Area = "A" | "B" | "C" | "D" | "E";

export const RADIUS: Record<Area, number> = {
  C: 0,
  B: 0.48,
  E: 0.62,
  A: 0.86,
  D: 0.86,
};

export function parseSensor(sensor: string): { area: Area; index: number } {
  const s = sensor.trim().toUpperCase();
  if (!s) throw new Error("empty sensor");
  const area = s[0] as Area;
  if (!"ABCDE".includes(area)) throw new Error(`unknown sensor area in ${sensor}`);
  if (area === "C") return { area: "C", index: 0 };
  const index = Number(s.slice(1));
  if (!Number.isInteger(index) || index < 1 || index > 8) {
    throw new Error(`bad sensor id ${sensor}`);
  }
  return { area, index };
}

export function formatSensor(area: Area, index: number): string {
  if (area === "C") return "C";
  return `${area}${index}`;
}

export function buttonToSensor(button: number): string {
  if (button < 1 || button > 8) throw new Error(`button must be 1..8, got ${button}`);
  return `A${button}`;
}

/** Math angle (radians): 0 = +X, pi/2 = +Y (up). Flip Y for canvas. */
export function sensorAngleRad(area: Area, index = 1): number {
  if (area === "C") return 0;
  if (area === "A" || area === "B") {
    return -index * (Math.PI / 4) + (5 * Math.PI) / 8;
  }
  if (area === "D" || area === "E") {
    return -index * (Math.PI / 4) + (6 * Math.PI) / 8;
  }
  throw new Error(`unknown area ${area}`);
}

/** Unit disk: x right, y up. */
export function sensorXY(sensor: string): { x: number; y: number } {
  const { area, index } = parseSensor(sensor);
  if (area === "C") return { x: 0, y: 0 };
  const ang = sensorAngleRad(area, index);
  const r = RADIUS[area];
  return { x: r * Math.cos(ang), y: r * Math.sin(ang) };
}

export function allSensors(): string[] {
  const out = ["C"];
  for (const area of ["A", "B", "D", "E"] as Area[]) {
    for (let i = 1; i <= 8; i++) out.push(`${area}${i}`);
  }
  return out;
}

/** Map unit (x,y up) into canvas pixels (y down). */
export function toCanvas(
  x: number,
  y: number,
  center: number,
  outerR: number,
): { x: number; y: number } {
  return {
    x: center + x * outerR,
    y: center - y * outerR,
  };
}
