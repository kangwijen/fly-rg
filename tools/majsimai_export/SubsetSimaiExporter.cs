using System.Globalization;
using System.Text.RegularExpressions;

namespace MajSimaiExport;

/// <summary>
/// Self-contained subset Simai exporter (same scope as fly_rg.chart.parse_simai_subset):
/// metadata, BPM, beat divisor, taps 1-8, break taps, holds, each (/).
/// Slides and touch notes are skipped with a warning.
/// </summary>
public static class SubsetSimaiExporter
{
    private static readonly Regex FieldRegex = new(
        @"&([^=&\r\n]+)=",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    public static ChartDocument Export(string maidataText, int? difficulty = null)
    {
        var fields = ParseFields(maidataText);
        var title = fields.GetValueOrDefault("title", "");
        var artist = fields.GetValueOrDefault("artist", "");
        var offset = ParseDouble(fields.GetValueOrDefault("first", "0"), 0.0);

        string? inote = null;
        if (difficulty is int d)
        {
            var inoteKey = $"inote_{d}";
            fields.TryGetValue(inoteKey, out inote);
            if (string.IsNullOrWhiteSpace(inote))
            {
                throw new InvalidOperationException(
                    $"Missing or empty &{inoteKey}= in maidata (use --difficulty).");
            }
        }
        else
        {
            inote = PickFirstInote(fields);
            if (string.IsNullOrWhiteSpace(inote))
            {
                throw new InvalidOperationException(
                    "No &inote_N= chart found in maidata (pass --difficulty).");
            }
        }

        var notes = ParseNotes(inote!, offset);
        return new ChartDocument
        {
            Title = title,
            Artist = artist,
            Offset = offset,
            Notes = notes,
        };
    }

    private static string? PickFirstInote(Dictionary<string, string> fields)
    {
        var bestLevel = int.MaxValue;
        string? best = null;
        foreach (var (key, value) in fields)
        {
            if (!key.StartsWith("inote_", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            if (!int.TryParse(key.AsSpan("inote_".Length), out var level))
            {
                continue;
            }

            if (string.IsNullOrWhiteSpace(value))
            {
                continue;
            }

            if (level < bestLevel)
            {
                bestLevel = level;
                best = value;
            }
        }

        return best;
    }

    internal static Dictionary<string, string> ParseFields(string text)
    {
        var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var matches = FieldRegex.Matches(text);
        for (var i = 0; i < matches.Count; i++)
        {
            var key = matches[i].Groups[1].Value.Trim();
            var valueStart = matches[i].Index + matches[i].Length;
            var valueEnd = i + 1 < matches.Count ? matches[i + 1].Index : text.Length;
            var value = text[valueStart..valueEnd].Trim();
            result[key] = value.TrimEnd();
        }

        return result;
    }

    internal static List<ChartNote> ParseNotes(string inote, double offset)
    {
        var notes = new List<ChartNote>();
        var i = 0;
        var n = inote.Length;
        double bpm = 0;
        double? divisor = null;
        double? absoluteStep = null;
        var time = offset;
        var warnedUnsupported = false;

        double StepSeconds()
        {
            if (absoluteStep.HasValue)
            {
                return absoluteStep.Value;
            }

            if (divisor.HasValue && bpm > 0)
            {
                return 240.0 / bpm / divisor.Value;
            }

            return 0;
        }

        while (i < n)
        {
            var c = inote[i];

            if (char.IsWhiteSpace(c) || c == '|')
            {
                if (c == '|' && i + 1 < n && inote[i + 1] == '|')
                {
                    while (i < n && inote[i] != '\n')
                    {
                        i++;
                    }

                    continue;
                }

                i++;
                continue;
            }

            if (c is 'E')
            {
                // End-of-chart marker when standing alone (not part of a note token).
                break;
            }

            if (c == '(')
            {
                i++;
                var bpmStr = ReadUntil(inote, ref i, ')');
                bpm = ParseDouble(bpmStr, bpm);
                continue;
            }

            if (c == '{')
            {
                i++;
                var body = ReadUntil(inote, ref i, '}');
                if (body.StartsWith('#'))
                {
                    absoluteStep = ParseDouble(body[1..], 0);
                    divisor = null;
                }
                else
                {
                    absoluteStep = null;
                    divisor = ParseDouble(body, 4);
                    if (bpm <= 0)
                    {
                        throw new InvalidOperationException("Beat divisor {n} requires a prior (bpm).");
                    }
                }

                continue;
            }

            if (c == ',')
            {
                time += StepSeconds();
                i++;
                continue;
            }

            if (c == '/')
            {
                i++;
                continue;
            }

            if (char.IsDigit(c))
            {
                var buttons = new List<int>();
                while (i < n && char.IsDigit(inote[i]))
                {
                    var digit = inote[i] - '0';
                    if (digit is < 1 or > 8)
                    {
                        throw new InvalidOperationException($"Button out of range at index {i}: {digit}");
                    }

                    buttons.Add(digit);
                    i++;
                }

                double? holdEnd = null;
                var skippedShape = false;

                while (i < n)
                {
                    var m = inote[i];
                    if (m is 'b' or 'B' or 'x' or 'X' or '$')
                    {
                        i++;
                        continue;
                    }

                    // EX tap uses trailing 'e' / "ex"; do not treat as chart end.
                    if (m is 'e')
                    {
                        i++;
                        continue;
                    }

                    if (m is 'h' or 'H')
                    {
                        i++;
                        if (i < n && inote[i] == '[')
                        {
                            i++;
                            var lenBody = ReadUntil(inote, ref i, ']');
                            holdEnd = time + ParseHoldLength(lenBody, bpm);
                        }

                        continue;
                    }

                    if (IsSlideOrTouchStart(m))
                    {
                        skippedShape = true;
                        i = SkipUnsupportedNoteTail(inote, i);
                        break;
                    }

                    break;
                }

                if (skippedShape)
                {
                    if (!warnedUnsupported)
                    {
                        Console.Error.WriteLine(
                            "Warning: slides/touch (and similar) are not exported by the subset parser; skipped.");
                        warnedUnsupported = true;
                    }
                }
                else
                {
                    foreach (var button in buttons)
                    {
                        notes.Add(new ChartNote
                        {
                            T = time,
                            Button = button,
                            Type = holdEnd.HasValue ? "hold" : "tap",
                            End = holdEnd,
                        });
                    }
                }

                continue;
            }

            if (!warnedUnsupported)
            {
                Console.Error.WriteLine($"Warning: skipping unsupported character '{c}' in inote.");
                warnedUnsupported = true;
            }

            i++;
        }

        notes.Sort((a, b) =>
        {
            var cmp = a.T.CompareTo(b.T);
            return cmp != 0 ? cmp : a.Button.CompareTo(b.Button);
        });
        return notes;
    }

    private static bool IsSlideOrTouchStart(char m) =>
        m is '-' or '^' or '<' or '>' or 'v' or 'V' or 'p' or 'q' or 's' or 'z' or 'w'
            or '*' or '@' or 'C' or 'f' or 'F';

    private static double ParseHoldLength(string body, double bpm)
    {
        body = body.Trim();
        if (body.StartsWith('#'))
        {
            return ParseDouble(body[1..], 0);
        }

        var parts = body.Split(':', 2);
        if (parts.Length != 2)
        {
            throw new InvalidOperationException($"Invalid hold length [{body}]");
        }

        var x = ParseDouble(parts[0], 4);
        var y = ParseDouble(parts[1], 1);
        if (bpm <= 0)
        {
            throw new InvalidOperationException("Hold [x:y] requires a prior (bpm).");
        }

        return 240.0 / bpm / x * y;
    }

    private static int SkipUnsupportedNoteTail(string text, int i)
    {
        while (i < text.Length)
        {
            var c = text[i];
            if (c is ',' or '/')
            {
                break;
            }

            if (c == '[')
            {
                i++;
                ReadUntil(text, ref i, ']');
                continue;
            }

            i++;
        }

        return i;
    }

    private static string ReadUntil(string text, ref int i, char closer)
    {
        var start = i;
        while (i < text.Length && text[i] != closer)
        {
            i++;
        }

        var value = text[start..i];
        if (i < text.Length && text[i] == closer)
        {
            i++;
        }

        return value.Trim();
    }

    private static double ParseDouble(string text, double fallback)
    {
        text = text.Trim();
        if (string.IsNullOrEmpty(text))
        {
            return fallback;
        }

        return double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out var value)
            ? value
            : fallback;
    }
}
