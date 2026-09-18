import { SIZE } from "./theme";

export function drawCover(
  ctx: CanvasRenderingContext2D,
  source: CanvasImageSource,
): void {
  const sw =
    "videoWidth" in source && (source as HTMLVideoElement).videoWidth
      ? (source as HTMLVideoElement).videoWidth
      : "naturalWidth" in source && (source as HTMLImageElement).naturalWidth
        ? (source as HTMLImageElement).naturalWidth
        : SIZE;
  const sh =
    "videoHeight" in source && (source as HTMLVideoElement).videoHeight
      ? (source as HTMLVideoElement).videoHeight
      : "naturalHeight" in source && (source as HTMLImageElement).naturalHeight
        ? (source as HTMLImageElement).naturalHeight
        : SIZE;
  if (!sw || !sh) return;
  const scale = Math.max(SIZE / sw, SIZE / sh);
  const dw = sw * scale;
  const dh = sh * scale;
  ctx.drawImage(source, (SIZE - dw) / 2, (SIZE - dh) / 2, dw, dh);
}

export function isVideoBackground(
  source: CanvasImageSource | null,
): source is HTMLVideoElement {
  return source instanceof HTMLVideoElement;
}
