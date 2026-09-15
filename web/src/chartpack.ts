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

  const trackMime = trackPath?.toLowerCase().endsWith(".mp3")
    ? "audio/mpeg"
    : trackPath?.toLowerCase().endsWith(".wav")
      ? "audio/wav"
      : "audio/ogg";
  const bgMime = bgPath?.toLowerCase().endsWith(".png") ? "image/png" : "image/jpeg";

  return {
    maidata,
    trackUrl: await blobUrl(trackPath, trackMime),
    trackName: trackPath ? baseName(trackPath) : null,
    bgUrl: await blobUrl(bgPath, bgMime),
    bgName: bgPath ? baseName(bgPath) : null,
    pvUrl: await blobUrl(pvPath, "video/mp4"),
    pvName: pvPath ? baseName(pvPath) : null,
    objectUrls,
  };
}

export function revokeChartPack(pack: ChartPack | null): void {
  if (!pack) return;
  for (const url of pack.objectUrls) {
    URL.revokeObjectURL(url);
  }
}
