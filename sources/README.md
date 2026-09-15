# Local maimai reference clones

This directory holds **read-only** shallow clones for sensor geometry and note-skin lookup. Clones are gitignored (`sources/*` except this README) and are **not** part of fly-rg.

Do not copy or vendor these trees into `web/` or `fly_rg/`. Recreate numbers and Canvas2D shapes in our own files.

[MajSimai](https://github.com/TeamMajdata/MajSimai) has no license file. The local clone here is for reading only; do not copy its sources into fly-rg.

## Present clones (shallow)

| Folder | Remote | Role |
| --- | --- | --- |
| `astrodx` | https://github.com/2394425147/astrodx | Skin Illustrator files under `Design/`; slide C# under `Scripts/` |
| `maipaddx` | https://github.com/2394425147/maipaddx | Same commit as `astrodx` at clone time (`590ab7d`) |
| `MajdataView` | https://github.com/LingFeng-bbben/MajdataView | Unity `GetAreaPos` and tap/hold/touch motion |
| `MajdataView_web` | https://github.com/TeamMajdata/MajdataView_web | Same `GetAreaPos` numbers as MajdataView |
| `SimaiSharp` | https://github.com/reflektone-games/SimaiSharp | Note groups A/B/C/D/E (no radii) |
| `MajSimai` | https://github.com/TeamMajdata/MajSimai | Read-only Simai parser |

Re-clone from repo root:

```text
git clone --depth 1 https://github.com/2394425147/astrodx.git sources/astrodx
git clone --depth 1 https://github.com/2394425147/maipaddx.git sources/maipaddx
git clone --depth 1 https://github.com/LingFeng-bbben/MajdataView.git sources/MajdataView
git clone --depth 1 https://github.com/TeamMajdata/MajdataView_web.git sources/MajdataView_web
git clone --depth 1 https://github.com/reflektone-games/SimaiSharp.git sources/SimaiSharp
git clone --depth 1 https://github.com/TeamMajdata/MajSimai.git sources/MajSimai
```

## Geometry cheat sheet (MajdataView TouchDrop.GetAreaPos)

Unity playfield: tap/hold land at distance **4.8**. Divide by 4.8 for unit-disk radii:

- C: 0
- B: 2.3 / 4.8 = **0.479**
- E: 3.0 / 4.8 = **0.625**
- A and D: 4.1 / 4.8 = **0.854**

Angles match what fly-rg already uses (A/B at `5*pi/8`, D/E at `6*pi/8`).

Hold body: sprite width **1.22**, inner clamp **1.225**, outer **4.8**. Tap scale grows with distance (`destScale = distance * 0.4 + 0.51`).
