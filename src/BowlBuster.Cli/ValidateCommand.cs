using BowlBuster.Catalog;
using BowlBuster.Chains;
using BowlBuster.Discs;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Replay;
using System.CommandLine;
using System.Text.Json;

namespace BowlBuster.Cli;

/// <summary>
/// <c>bowlbuster recordings validate</c>: replays a recording the harness wrote, and says whether it can be used.
/// </summary>
internal static class ValidateCommand
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true, PropertyNamingPolicy = JsonNamingPolicy.CamelCase };

    /// <summary>The environment variable naming the extracted disc when <c>--disc</c> doesn't.</summary>
    public const string DiscVariable = "BOWL_DISC";

    private const int NamedDifferences = 5;

    public static Command Build(TextWriter output, TextWriter error, Func<DirectoryInfo?, Vocabulary> vocabulary)
    {
        Argument<DirectoryInfo> recording = new("recording") { Description = "The recording's directory." };
        Option<bool> json = new("--json") { Description = "Print the result as JSON." };
        Option<DirectoryInfo?> catalog = new("--catalog") { Description = "The catalog directory, to name the costumes a load wore." };
        Option<DirectoryInfo?> disc = new("--disc") { Description = $"The extracted disc, to check the recording's layer blocks against; else {DiscVariable}." };

        Command command = new("validate", "Replay a recording and say whether it can be used.") { recording, json, catalog, disc };
        command.SetAction(parsed => Run(
            parsed.GetRequiredValue(recording),
            parsed.GetValue(catalog),
            parsed.GetValue(disc) ?? DiscFromEnvironment(),
            parsed.GetValue(json),
            output,
            error,
            vocabulary));
        return command;
    }

    private static DirectoryInfo? DiscFromEnvironment() =>
        Environment.GetEnvironmentVariable(DiscVariable) is { Length: > 0 } named ? new DirectoryInfo(named) : null;

    private static int Run(DirectoryInfo directory, DirectoryInfo? catalog, DirectoryInfo? disc, bool asJson, TextWriter output, TextWriter error, Func<DirectoryInfo?, Vocabulary> vocabulary)
    {
        if (disc is { Exists: false })
        {
            error.WriteLine($"Cannot read the disc: {disc.FullName} isn't a directory.");
            return CommandLineApp.Unreadable;
        }

        Recording recording;
        try
        {
            recording = RecordingDirectory.Read(directory.FullName, vocabulary(catalog));
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or FormatException or CatalogException)
        {
            error.WriteLine($"Cannot read the recording: {exception.Message}");
            return CommandLineApp.Unreadable;
        }

        PlatformProfile profile = PlatformProfile.XboxNtscU;
        FileCaptureSource captures = new(directory.FullName);
        RecordingValidation result = new ReplayValidator(profile, captures).Validate(recording);
        IReadOnlyList<LayerComparison>? layers = result.IsAccepted && disc is not null
            ? new LayerCheck(profile, new DiscLayers(disc.FullName, profile), captures).Compare(recording)
            : null;

        if (asJson) output.WriteLine(JsonSerializer.Serialize(Describe(recording, result, layers), JsonOptions));
        else if (result.IsAccepted)
        {
            WriteAccepted(recording, output);
            if (layers is not null) WriteLayers(layers, output);
        }
        else error.WriteLine($"Rejected {recording.Id}: {result.Rejection}");

        return result.IsAccepted ? CommandLineApp.Success : CommandLineApp.Rejected;
    }

    private static void WriteAccepted(Recording recording, TextWriter output)
    {
        int loads = recording.Segments.Sum(static segment => segment.Loads.Count);
        output.WriteLine($"Accepted {recording.Id} ({recording.Platform}): {recording.Segments.Count} segment(s), {loads} load(s).");

        foreach (RecordingSegment segment in recording.Segments)
        {
            output.WriteLine($"Segment {segment.Index}");
            foreach (RecordedLoad load in segment.Loads)
            {
                string number = load.Load is { } known ? $"load {known.Value}" : "boot scene";
                string cutoff = load.Heap.Cutoff is { } point ? $", cutoff after {point.RequestCount}{(point.CaptureId is { } capture ? $" (capture {capture})" : "")}" : "";
                output.WriteLine($"  {load.Key.Scene}  counter {load.Counter}  {number}  {Costumes(load.Key.Costumes)}  {load.Heap.Requests.Count} request(s){cutoff}");
            }
        }
    }

    private static void WriteLayers(IReadOnlyList<LayerComparison> layers, TextWriter output)
    {
        output.WriteLine($"Layers ({layers.Count(static layer => layer.Match is LayerMatch.Same)} of {layers.Count} the same as on disc)");
        foreach (LayerComparison layer in layers)
            output.WriteLine($"  {layer.Layer.Archive} layer {layer.Layer.Layer}  counter {layer.Load.Counter} op {layer.Op}  {Summary(layer)}");
    }

    private static string Summary(LayerComparison layer) => layer.Match switch
    {
        LayerMatch.Same => "same",
        LayerMatch.NotOnDisc => "not on disc",
        LayerMatch.NotCaptured => "not captured",
        _ => $"differs in {layer.Differences.Count} word(s): "
            + string.Join(", ", layer.Differences.Take(NamedDifferences).Select(static word => $"{word.Asset ?? "padding"} +0x{word.OffsetInAsset:X}"))
            + (layer.Differences.Count > NamedDifferences ? ", ..." : ""),
    };

    private static string Costumes(Costumes costumes) => $"{costumes.Spongebob ?? "-"} / {costumes.Patrick ?? "-"}";

    private static object Describe(Recording recording, RecordingValidation result, IReadOnlyList<LayerComparison>? layers) => result.IsAccepted
        ? new AcceptedResult(
            true,
            recording.Id,
            recording.Platform,
            [.. recording.Segments.Select(static segment => new SegmentResult(segment.Index, [.. segment.Loads.Select(Describe)]))],
            layers?.Select(Describe).ToList())
        : new RejectedResult(false, recording.Id, recording.Platform, Describe(result.Rejection));

    private static LayerResult Describe(LayerComparison layer) => new(
        layer.Segment,
        layer.Load.Counter,
        layer.Op,
        layer.Layer.Archive,
        layer.Layer.Layer,
        layer.Address,
        layer.Size,
        JsonNamingPolicy.CamelCase.ConvertName(layer.Match.ToString()),
        [.. layer.Differences.Select(static word => new DifferenceResult(word.Offset, word.Captured, word.OnDisc, word.Asset, word.OffsetInAsset))]);

    private static LoadResult Describe(RecordedLoad load) => new(
        load.Key.Scene,
        load.Counter,
        load.Load?.Value,
        load.Key.Costumes.Spongebob,
        load.Key.Costumes.Patrick,
        load.Heap.Requests.Count,
        load.Heap.Cutoff?.RequestCount,
        load.Heap.Cutoff?.CaptureId);

    private static MismatchResult Describe(ReplayMismatch mismatch) => new(
        mismatch.Check.ToString(),
        mismatch.Site?.Segment,
        mismatch.Site?.Load.Key.Scene,
        mismatch.Site?.Load.Counter,
        mismatch.Site?.Op,
        mismatch.Site?.Request?.ToString(),
        mismatch.Difference?.Field,
        mismatch.Difference?.Value,
        mismatch.Difference?.OtherValue,
        mismatch.Detail,
        mismatch.ToString());

    private sealed record AcceptedResult(bool Accepted, string Run, string Platform, IReadOnlyList<SegmentResult> Segments, IReadOnlyList<LayerResult>? Layers);

    private sealed record LayerResult(int Segment, int Counter, int Op, string Archive, int Layer, uint Address, uint Size, string Match, IReadOnlyList<DifferenceResult> Differences);

    private sealed record DifferenceResult(uint Offset, uint Captured, uint OnDisc, string? Asset, uint OffsetInAsset);

    private sealed record RejectedResult(bool Accepted, string Run, string Platform, MismatchResult Mismatch);

    private sealed record SegmentResult(int Index, IReadOnlyList<LoadResult> Loads);

    private sealed record LoadResult(string Scene, int Counter, int? Load, string? Spongebob, string? Patrick, int Requests, int? CutoffAfter, string? Capture);

    private sealed record MismatchResult(string Check, int? Segment, string? Scene, int? Counter, int? Op, string? Request, string? Field, uint? Recorded, uint? Replayed, string? Detail, string Text);
}
