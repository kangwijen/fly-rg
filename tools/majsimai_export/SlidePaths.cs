namespace MajSimaiExport;

/// <summary>
/// Basic slide path tables matching fly_rg.slides (shapes - &gt; &lt; ^ v V).
/// </summary>
public static class SlidePaths
{
    public static readonly HashSet<char> SupportedShapes = ['-', '>', '<', '^', 'v', 'V'];

    public static List<string> Expand(char shape, int start, int end)
    {
        if (!SupportedShapes.Contains(shape))
        {
            throw new ArgumentException($"unsupported slide shape {shape}");
        }

        if (start is < 1 or > 8 || end is < 1 or > 8)
        {
            throw new ArgumentException($"slide buttons must be 1..8, got {start}->{end}");
        }

        return shape switch
        {
            '-' => Straight(start, end),
            '>' => ARing(start, end, clockwise: true),
            '<' => ARing(start, end, clockwise: false),
            _ => Curve(shape, start, end),
        };
    }

    private static List<string> Straight(int start, int end)
    {
        if (start == end)
        {
            throw new ArgumentException("straight slide requires distinct start and end");
        }

        return [$"A{start}", $"B{start}", "C", $"B{end}", $"A{end}"];
    }

    private static int Next(int button, bool clockwise) =>
        clockwise ? button % 8 + 1 : (button == 1 ? 8 : button - 1);

    private static List<string> ARing(int start, int end, bool clockwise)
    {
        var path = new List<string> { $"A{start}" };
        var cur = start;
        if (start == end)
        {
            for (var i = 0; i < 8; i++)
            {
                cur = Next(cur, clockwise);
                path.Add($"A{cur}");
            }

            return path;
        }

        while (cur != end)
        {
            cur = Next(cur, clockwise);
            path.Add($"A{cur}");
        }

        return path;
    }

    private static List<int> ArcButtons(int start, int end, bool clockwise)
    {
        var buttons = new List<int> { start };
        var cur = start;
        if (start == end)
        {
            for (var i = 0; i < 8; i++)
            {
                cur = Next(cur, clockwise);
                buttons.Add(cur);
            }

            return buttons;
        }

        while (cur != end)
        {
            cur = Next(cur, clockwise);
            buttons.Add(cur);
        }

        return buttons;
    }

    private static bool ShortClockwise(int start, int end)
    {
        if (start == end)
        {
            return true;
        }

        var cw = (end - start + 8) % 8;
        var ccw = (start - end + 8) % 8;
        return cw <= ccw;
    }

    private static List<string> Curve(char shape, int start, int end)
    {
        var clockwise = shape == 'V' ? !ShortClockwise(start, end) : ShortClockwise(start, end);
        var buttons = ArcButtons(start, end, clockwise);
        if (buttons.Count == 1)
        {
            return [$"A{start}"];
        }

        if (shape == '^')
        {
            var path = new List<string> { $"A{buttons[0]}" };
            for (var i = 1; i < buttons.Count - 1; i++)
            {
                path.Add($"B{buttons[i]}");
            }

            path.Add($"A{buttons[^1]}");
            return path;
        }

        if (shape == 'v')
        {
            var path = new List<string> { $"A{buttons[0]}" };
            for (var i = 1; i < buttons.Count - 1; i++)
            {
                path.Add($"A{buttons[i]}");
                path.Add($"B{buttons[i]}");
            }

            path.Add($"A{buttons[^1]}");
            return path;
        }

        // V
        var vPath = buttons.Take(buttons.Count - 1).Select(b => $"A{b}").ToList();
        if (buttons.Count >= 2)
        {
            vPath.Add($"B{buttons[^2]}");
        }

        vPath.Add($"A{buttons[^1]}");
        return vPath;
    }
}
