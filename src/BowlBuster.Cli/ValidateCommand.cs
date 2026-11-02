using BowlBuster.Catalog;
using BowlBuster.Chains;
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

    public static Command Build(TextWriter output, TextWriter error, Func<DirectoryInfo?, Vocabulary> vocabulary)
    {
        Argument<DirectoryInfo> recording = new("recording") { Description = "The recording's directory." };
        Option<bool> json = new("--json") { Description = "Print the result as JSON." };
        Option<DirectoryInfo?> catalog = new("--catalog") { Description = "The catalog directory, to name the costumes a load wore." };

        Command command = new("validate", "Replay a recording and say whether it can be used.") { recording, json, catalog };
        command.SetAction(parsed => Run(parsed.GetRequiredValue(recording), parsed.GetValue(catalog), parsed.GetValue(json), output, error, vocabulary));
        return command;
    }

    private static int Run(DirectoryInfo directory, DirectoryInfo? catalog, bool asJson, TextWriter output, TextWriter error, Func<DirectoryInfo?, Vocabulary> vocabulary)
    {
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

        RecordingValidation result = new ReplayValidator(PlatformProfile.XboxNtscU, new FileCaptureSource(directory.FullName)).Validate(recording);

        if (asJson) output.WriteLine(JsonSerializer.Serialize(Describe(recording, result), JsonOptions));
        else if (result.IsAccepted) WriteAccepted(recording, output);
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

    private static string Costumes(Costumes costumes) => $"{costumes.Spongebob ?? "-"} / {costumes.Patrick ?? "-"}";

    private static object Describe(Recording recording, RecordingValidation result) => result.IsAccepted
        ? new AcceptedResult(true, recording.Id, recording.Platform, [.. recording.Segments.Select(static segment => new SegmentResult(segment.Index, [.. segment.Loads.Select(Describe)]))])
        : new RejectedResult(false, recording.Id, recording.Platform, Describe(result.Rejection));

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

    private sealed record AcceptedResult(bool Accepted, string Run, string Platform, IReadOnlyList<SegmentResult> Segments);

    private sealed record RejectedResult(bool Accepted, string Run, string Platform, MismatchResult Mismatch);

    private sealed record SegmentResult(int Index, IReadOnlyList<LoadResult> Loads);

    private sealed record LoadResult(string Scene, int Counter, int? Load, string? Spongebob, string? Patrick, int Requests, int? CutoffAfter, string? Capture);

    private sealed record MismatchResult(string Check, int? Segment, string? Scene, int? Counter, int? Op, string? Request, string? Field, uint? Recorded, uint? Replayed, string? Detail, string Text);
}
