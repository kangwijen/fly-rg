using System.Text.Json.Serialization;

namespace MajSimaiExport;

public sealed class ChartDocument
{
    [JsonPropertyName("title")]
    public string Title { get; set; } = "";

    [JsonPropertyName("artist")]
    public string Artist { get; set; } = "";

    [JsonPropertyName("offset")]
    public double Offset { get; set; }

    [JsonPropertyName("notes")]
    public List<ChartNote> Notes { get; set; } = [];
}

public sealed class ChartNote
{
    [JsonPropertyName("t")]
    public double T { get; set; }

    [JsonPropertyName("button")]
    public int Button { get; set; }

    [JsonPropertyName("type")]
    public string Type { get; set; } = "tap";

    [JsonPropertyName("end")]
    public double? End { get; set; }
}
