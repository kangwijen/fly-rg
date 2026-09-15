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

    [JsonPropertyName("type")]
    public string Type { get; set; } = "tap";

    [JsonPropertyName("sensor")]
    public string Sensor { get; set; } = "";

    [JsonPropertyName("button")]
    public int? Button { get; set; }

    [JsonPropertyName("end")]
    public double? End { get; set; }

    [JsonPropertyName("slide")]
    public SlideInfo? Slide { get; set; }
}

public sealed class SlideInfo
{
    [JsonPropertyName("shape")]
    public string Shape { get; set; } = "-";

    [JsonPropertyName("end_sensor")]
    public string EndSensor { get; set; } = "";

    [JsonPropertyName("path")]
    public List<string> Path { get; set; } = [];

    [JsonPropertyName("end_t")]
    public double EndT { get; set; }
}
