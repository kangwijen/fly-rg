import JSZip from "jszip";

export type ChartPack = {
  maidata: string;
  trackUrl: string | null;
  trackName: string | null;
  bgUrl: string | null;
  bgName: string | null;
  pvUrl: string | null;
  pvName: string | null;
  objectUrls: string[];
};

function baseName(path: string): string {
  const parts = path.replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || path;
}

function findEntry(names: string[], candidates: string[]): string | null {
  const lower = new Map(names.map((n) => [baseName(n).toLowerCase(), n]));
  for (const c of candidates) {
    const hit = lower.get(c.toLowerCase());
    if (hit) return hit;
  }
  // fallback: any file ending with the name
  for (const c of candidates) {
    const suffix = c.toLowerCase();
    for (const n of names) {
      if (baseName(n).toLowerCase() === suffix) return n;
      if (baseName(n).toLowerCase().endsWith(suffix) && suffix.includes(".")) {
        return n;
      }
    }
  }
  return null;
}

function trackMimeFor(path: string | null): string {
  if (!path) return "audio/ogg";
  const lower = path.toLowerCase();
  if (lower.endsWith(".mp3")) return "audio/mpeg";
  if (lower.endsWith(".wav")) return "audio/wav";
  return "audio/ogg";
}

function bgMimeFor(path: string | null): string {
  if (!path) return "image/jpeg";
  const lower = path.toLowerCase();
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".webp")) return "image/webp";
  return "image/jpeg";
}

function pvMimeFor(path: string | null): string {
  if (!path) return "video/mp4";
  if (path.toLowerCase().endsWith(".webm")) return "video/webm";
  return "video/mp4";
}

/**
 * Unpack a Majdata-style chart zip (folder optional):
 * maidata.txt, track.ogg|mp3, bg.png|jpg, pv.mp4 (optional).
 */
export async function unpackChartZip(file: File): Promise<ChartPack> {
  const zip = await JSZip.loadAsync(file);
  const names = Object.keys(zip.files).filter((n) => !zip.files[n].dir);
  const objectUrls: string[] = [];

  const maidataPath = findEntry(names, ["maidata.txt"]);
  if (!maidataPath) {
    throw new Error("Zip missing maidata.txt");
  }
  const maidata = await zip.files[maidataPath].async("string");

  async function blobUrl(path: string | null, mime: string): Promise<string | null> {
    if (!path) return null;
    const buf = await zip.files[path].async("blob");
    const typed = buf.type ? buf : new Blob([buf], { type: mime });
    const url = URL.createObjectURL(typed);
    objectUrls.push(url);
    return url;
  }

  const trackPath = findEntry(names, ["track.ogg", "track.mp3", "track.wav"]);
  const bgPath = findEntry(names, ["bg.png", "bg.jpg", "bg.jpeg", "bg.webp"]);
  const pvPath = findEntry(names, ["pv.mp4", "pv.webm"]);

  try {
    const trackUrl = await blobUrl(trackPath, trackMimeFor(trackPath));
    const bgUrl = await blobUrl(bgPath, bgMimeFor(bgPath));
    const pvUrl = await blobUrl(pvPath, pvMimeFor(pvPath));

    return {
      maidata,
      trackUrl,
      trackName: trackPath ? baseName(trackPath) : null,
      bgUrl,
      bgName: bgPath ? baseName(bgPath) : null,
      pvUrl,
      pvName: pvPath ? baseName(pvPath) : null,
      objectUrls,
    };
  } catch (err) {
    for (const url of objectUrls) {
      URL.revokeObjectURL(url);
    }
    throw err;
  }
}

export function revokeChartPack(pack: ChartPack | null): void {
  if (!pack) return;
  for (const url of pack.objectUrls) {
    URL.revokeObjectURL(url);
  }
}
