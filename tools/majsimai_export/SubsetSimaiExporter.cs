using System.Globalization;
using System.Text.RegularExpressions;

namespace MajSimaiExport;

/// <summary>
/// Self-contained subset Simai exporter (same scope as fly_rg.chart.parse_simai_subset):
/// metadata, BPM, beat divisor, taps 1-8, break taps, holds, touch, touch hold,
/// basic slides (- &gt; &lt; ^ v V), each (/).
/// Wifi / exotic slides are skipped with a warning.
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

        void WarnOnce(string message)
        {
            if (warnedUnsupported)
            {
                return;
            }

            Console.Error.WriteLine(message);
            warnedUnsupported = true;
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

            if ((c is 'E' or 'e')
                && !(i + 1 < n && (char.IsDigit(inote[i + 1]) || inote[i + 1] is 'h' or 'H' or 'f' or 'F')))
            {
                // Bare E ends the chart; E1..E8 / Eh / Ef are touch notes.
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

            // Touch / touch hold: A1, B2f, C, A1h[8:1]
            if (c is >= 'A' and <= 'E' or >= 'a' and <= 'e')
            {
                var area = char.ToUpperInvariant(c);
                i++;
                int? index = null;
                if (i < n && inote[i] is >= '1' and <= '8')
                {
                    index = inote[i] - '0';
                    i++;
                }

                if (i < n && inote[i] is 'f' or 'F')
                {
                    i++;
                }

                string sensor;
                try
                {
                    sensor = NormalizeTouchSensor(area, index);
                }
                catch (Exception)
                {
                    WarnOnce($"Warning: skipping bad touch near index {i}.");
                    continue;
                }

                double? holdEnd = null;
                var isHold = false;
                if (i < n && inote[i] is 'h' or 'H')
                {
                    isHold = true;
                    i++;
                    if (i < n && inote[i] == '[')
                    {
                        i++;
                        var lenBody = ReadUntil(inote, ref i, ']');
                        holdEnd = time + ParseHoldLength(lenBody, bpm);
                    }
                }

                notes.Add(new ChartNote
                {
                    T = time,
                    Type = isHold ? "touch_hold" : "touch",
                    Sensor = sensor,
                    Button = ButtonFromSensor(sensor),
                    End = holdEnd,
                });
                continue;
            }

            if (char.IsDigit(c))
            {
                var startButton = c - '0';
                if (startButton is < 1 or > 8)
                {
                    throw new InvalidOperationException($"Button out of range at index {i}: {startButton}");
                }

                i++;
                // Optional break marker.
                if (i < n && inote[i] is 'b' or 'B')
                {
                    i++;
                }

                // Hold: h[...]
                if (i < n && inote[i] is 'h' or 'H')
                {
                    i++;
                    double? holdEnd = null;
                    if (i < n && inote[i] == '[')
                    {
                        i++;
                        var lenBody = ReadUntil(inote, ref i, ']');
                        holdEnd = time + ParseHoldLength(lenBody, bpm);
                    }

                    notes.Add(new ChartNote
                    {
                        T = time,
                        Type = "hold",
                        Sensor = $"A{startButton}",
                        Button = startButton,
                        End = holdEnd,
                    });
                    continue;
                }

                // Basic slide: shape + end + [len]
                if (i < n && SlidePaths.SupportedShapes.Contains(inote[i]))
                {
                    var shape = inote[i];
                    i++;
                    if (i >= n || inote[i] is < '1' or > '8')
                    {
                        WarnOnce("Warning: skipping malformed slide (missing end button).");
                        i = SkipUnsupportedNoteTail(inote, i);
                        continue;
                    }

                    var endButton = inote[i] - '0';
                    i++;
                    if (i >= n || inote[i] != '[')
                    {
                        WarnOnce("Warning: skipping slide without duration [...].");
                        i = SkipUnsupportedNoteTail(inote, i);
                        continue;
                    }

                    i++;
                    var lenBody = ReadUntil(inote, ref i, ']');
                    var dur = ParseHoldLength(lenBody, bpm);
                    List<string> path;
                    try
                    {
                        path = SlidePaths.Expand(shape, startButton, endButton);
                    }
                    catch (Exception ex)
                    {
                        WarnOnce($"Warning: skipping slide: {ex.Message}");
                        continue;
                    }

                    var endT = time + dur;
                    notes.Add(new ChartNote
                    {
                        T = time,
                        Type = "slide",
                        Sensor = path[0],
                        Button = startButton,
                        End = endT,
                        Slide = new SlideInfo
                        {
                            Shape = shape.ToString(),
                            EndSensor = path[^1],
                            Path = path,
                            EndT = endT,
                        },
                    });
                    continue;
                }

                // Exotic / multi-char slides after digit.
                if (i < n && IsExoticSlideStart(inote[i]))
                {
                    WarnOnce("Warning: wifi/exotic slides are not exported by the subset parser; skipped.");
                    i = SkipUnsupportedNoteTail(inote, i);
                    continue;
                }

                // Plain tap (and multi-digit each like 15 without slash — rare; take single digit).
                notes.Add(new ChartNote
                {
                    T = time,
                    Type = "tap",
                    Sensor = $"A{startButton}",
                    Button = startButton,
                    End = null,
                });
                continue;
            }

            WarnOnce($"Warning: skipping unsupported character '{c}' in inote.");
            i++;
        }

        notes.Sort((a, b) =>
        {
            var cmp = a.T.CompareTo(b.T);
            if (cmp != 0)
            {
                return cmp;
            }

            cmp = string.CompareOrdinal(a.Sensor, b.Sensor);
            if (cmp != 0)
            {
                return cmp;
            }

            return Nullable.Compare(a.Button, b.Button);
        });
        return notes;
    }

    private static string NormalizeTouchSensor(char area, int? index)
    {
        if (area == 'C')
        {
            return "C";
        }

        if (index is null)
        {
            throw new InvalidOperationException($"touch area {area} requires index 1..8");
        }

        return $"{area}{index.Value}";
    }

    private static int? ButtonFromSensor(string sensor)
    {
        if (sensor.Length >= 2 && sensor[0] == 'A' && int.TryParse(sensor[1..], out var b) && b is >= 1 and <= 8)
        {
            return b;
        }

        return null;
    }

    private static bool IsExoticSlideStart(char m) =>
        m is 'p' or 'q' or 's' or 'z' or 'w' or 'P' or 'Q' or 'S' or 'Z' or 'W' or '*' or '@';

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
