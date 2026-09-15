using System.Text.Json;
using MajSimaiExport;

static int Usage()
{
    Console.Error.WriteLine(
        "Usage: majsimai_export <maidata.txt> [-o out.json] [--difficulty N]");
    Console.Error.WriteLine(
        "  If --difficulty is omitted, the lowest &inote_N= chart is used.");
    return 2;
}

if (args.Length == 0 || args is ["-h"] or ["--help"] or ["/?"] )
{
    return Usage();
}

string? inputPath = null;
string? outputPath = null;
int? difficulty = null;

for (var i = 0; i < args.Length; i++)
{
    var arg = args[i];
    switch (arg)
    {
        case "-o":
        case "--output":
            if (i + 1 >= args.Length)
            {
                Console.Error.WriteLine("Missing value for -o");
                return Usage();
            }

            outputPath = args[++i];
            break;
        case "--difficulty":
        case "-d":
            if (i + 1 >= args.Length)
            {
                Console.Error.WriteLine("Missing value for --difficulty");
                return Usage();
            }

            if (!int.TryParse(args[++i], out var d))
            {
                Console.Error.WriteLine("Invalid --difficulty value");
                return Usage();
            }

            difficulty = d;
            break;
        case "-h":
        case "--help":
            return Usage();
        default:
            if (arg.StartsWith('-'))
            {
                Console.Error.WriteLine($"Unknown option: {arg}");
                return Usage();
            }

            if (inputPath is not null)
            {
                Console.Error.WriteLine("Multiple input paths given");
                return Usage();
            }

            inputPath = arg;
            break;
    }
}

if (inputPath is null)
{
    return Usage();
}

if (!File.Exists(inputPath))
{
    Console.Error.WriteLine($"File not found: {inputPath}");
    return 1;
}

try
{
    var text = File.ReadAllText(inputPath);
    // Default path: self-contained subset exporter (no MajSimai reference required).
    // See README "Full MajSimai" to swap in TeamMajdata/MajSimai for slides/touch.
    var chart = SubsetSimaiExporter.Export(text, difficulty);

    var json = JsonSerializer.Serialize(
        chart,
        new JsonSerializerOptions
        {
            WriteIndented = true,
            // Keep "end": null in output to match the shared chart schema.
            DefaultIgnoreCondition = System.Text.Json.Serialization.JsonIgnoreCondition.Never,
        });

    if (outputPath is null)
    {
        Console.WriteLine(json);
    }
    else
    {
        var dir = Path.GetDirectoryName(Path.GetFullPath(outputPath));
        if (!string.IsNullOrEmpty(dir))
        {
            Directory.CreateDirectory(dir);
        }

        File.WriteAllText(outputPath, json + Environment.NewLine);
        Console.Error.WriteLine($"Wrote {chart.Notes.Count} notes to {outputPath}");
    }

    return 0;
}
catch (Exception ex)
{
    Console.Error.WriteLine(ex.Message);
    return 1;
}
