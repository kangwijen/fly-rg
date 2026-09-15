# majsimai_export

Optional .NET 8 console tool that converts Simai `maidata.txt` into the fly-rg timed-note JSON schema.

This project builds **without** MajSimai. The default path is a self-contained **subset** exporter with the same capabilities as the Python `parse_simai_subset` loader:

- Metadata: `&title=`, `&artist=`, `&first=` (maps to JSON `offset`)
- Timing: `(bpm)`, `{divisor}`, `{#seconds}`
- Notes: taps `1`..`8`, break `1b`, holds `1h[x:y]` / `1h[#seconds]`, each `/`
- Slides and touch are skipped (warning on stderr)

Python already ships its own subset parser, so this tool is optional (handy for CI, bulk export, or a future full MajSimai bridge).

## Requirements

- [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0) (or a newer SDK that can target `net8.0`)

## Build

```bash
cd tools/majsimai_export
dotnet build -c Release
```

## Run

```bash
dotnet run -c Release -- ../../charts/demo/maidata.txt -o ../../charts/demo/chart.json
```

Or after build:

```bash
dotnet tools/majsimai_export/bin/Release/net8.0/majsimai_export.dll charts/demo/maidata.txt -o out.json
```

CLI:

```text
majsimai_export <maidata.txt> [-o out.json] [--difficulty N]
```

If `--difficulty` is omitted, the lowest `&inote_N=` chart is used. If `-o` is omitted, JSON is written to stdout.

## Output schema

```json
{
  "title": "",
  "artist": "",
  "offset": 0.0,
  "notes": [
    { "t": 0.0, "button": 1, "type": "tap", "end": null }
  ]
}
```

`type` is `"tap"` or `"hold"`. Holds set `end` to the release time in seconds.

## Full MajSimai

[MajSimai](https://github.com/TeamMajdata/MajSimai) has **no license file** in its repository. Do **not** copy or vendor its sources into fly-rg.

To swap in MajSimai later for slides/touch:

1. Clone beside this repo (example layout):

   ```text
   github-repos/random/fly-rg/
   github-repos/random/MajSimai/    # or any path
   ```

2. Set `MajSimaiPath` when building (defaults to `../../../MajSimai` relative to the `.csproj`):

   ```bash
   dotnet build -c Release -p:MajSimaiPath=C:\path\to\MajSimai
   ```

3. Uncomment the conditional `ProjectReference` in `majsimai_export.csproj`.

4. Change `Program.cs` to call MajSimai APIs and map `SimaiNote` (and related) into the same JSON schema above. Keep the subset exporter as a fallback for CI machines that do not have the clone.

Until that wiring exists, subset mode is the supported path.
