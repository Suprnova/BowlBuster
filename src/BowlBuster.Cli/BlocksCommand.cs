using BowlBuster.Catalog;
using BowlBuster.Discs;
using BowlBuster.Landings;
using BowlBuster.Platforms;
using System.CommandLine;
using System.Text.Json;

namespace BowlBuster.Cli;

/// <summary>
/// <c>bowlbuster recordings blocks</c>: lists the live blocks at each captured cutoff of a recording and how far each is
/// named, which measures block naming.
/// </summary>
internal static class BlocksCommand
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true, PropertyNamingPolicy = JsonNamingPolicy.CamelCase };

    public static Command Build(TextWriter output, TextWriter error)
    {
        Argument<DirectoryInfo> recording = new("recording") { Description = "The recording's directory." };
        Option<bool> json = new("--json") { Description = "Print the result as JSON." };
        Option<DirectoryInfo?> disc = RecordingInputs.DiscOption("to name the layer blocks from");

        Command command = new("blocks", "List the live blocks at each captured cutoff and how far each is named.") { recording, json, disc };
        command.SetAction(parsed => Run(
            parsed.GetRequiredValue(recording),
            RecordingInputs.Disc(parsed.GetValue(disc)),
            parsed.GetValue(json),
            output,
            error));
        return command;
    }

    private static int Run(DirectoryInfo directory, DirectoryInfo? disc, bool asJson, TextWriter output, TextWriter error)
    {
        if (RecordingInputs.Read(directory, disc, static () => Vocabulary.Empty, error) is not { Recording: var recording } replayed)
            return CommandLineApp.Unreadable;

        if (!replayed.Result.IsAccepted)
        {
            error.WriteLine($"Rejected {recording.Id}: {replayed.Result.Rejection}");
            return replayed.ExitCode;
        }

        PlatformProfile profile = PlatformProfile.XboxNtscU;
        RegionNamer namer = new(profile, disc is null ? null : new DiscLayers(disc.FullName, profile));
        IReadOnlyList<LoadNaming> loads = new NamingCoverage(profile, namer, replayed.Captures).Measure(recording);
        IReadOnlyList<CallerResult> callers = ByCaller(loads);

        if (asJson) output.WriteLine(JsonSerializer.Serialize(new BlocksResult(recording.Id, [.. loads.Select(Describe)], callers), JsonOptions));
        else Write(recording.Id, loads, callers, output);

        return CommandLineApp.Success;
    }

    private static void Write(string run, IReadOnlyList<LoadNaming> loads, IReadOnlyList<CallerResult> callers, TextWriter output)
    {
        output.WriteLine($"Blocks of {run}: {loads.Count} captured cutoff(s), {Named(loads.SelectMany(static load => load.Blocks))} named");
        foreach (LoadNaming load in loads)
        {
            output.WriteLine($"Segment {load.Segment}  {load.Load.Key.Scene}  counter {load.Load.Counter}  {load.Blocks.Count} block(s), {Named(load.Blocks)} named");
            foreach (BlockNaming block in load.Blocks)
            {
                string layer = block.Block.Request.Layer is { } id ? $"  {id.Archive} layer {id.Layer}" : "";
                output.WriteLine($"  op {block.Block.Op}  0x{block.Block.Request.Caller:X}  0x{block.Block.Address:X}  size 0x{block.Block.Size:X}  {Kind(block.First)}{layer}  {Depths(block)}");
            }
        }

        output.WriteLine("By caller, most unnamed bytes first");
        foreach (CallerResult caller in callers)
            output.WriteLine($"  0x{caller.Caller:X}  {caller.Blocks} block(s)  0x{caller.Bytes:X} bytes  {Percent(caller.Named, caller.Bytes)} named");
    }

    private static string Kind(RegionName name) => name switch
    {
        LayerAssetName or LayerPaddingName or LayerSlackName => "layer",
        LiveObjectName live => $"live {live.Type.Name}",
        _ => "unknown",
    };

    private static string Depths(BlockNaming block) => string.Join(
        ", ",
        block.Bytes.OrderBy(static depth => depth.Key).Select(depth => $"{Label(depth.Key)} {Percent(depth.Value, block.Block.Size)}"));

    private static string Named(IEnumerable<BlockNaming> blocks)
    {
        BlockNaming[] all = [.. blocks];
        return Percent(all.Sum(static block => (long)NamedBytes(block)), all.Sum(static block => (long)block.Block.Size));
    }

    private static uint NamedBytes(BlockNaming block) =>
        (uint)block.Bytes.Where(static depth => depth.Key is not NamingDepth.Caller).Sum(static depth => (long)depth.Value);

    private static string Percent(long part, long whole) => whole is 0 ? "-" : $"{100.0 * part / whole:0.0}%";

    private static string Label(NamingDepth depth) => JsonNamingPolicy.CamelCase.ConvertName(depth.ToString());

    private static IReadOnlyList<CallerResult> ByCaller(IReadOnlyList<LoadNaming> loads) =>
    [
        .. loads
            .SelectMany(static load => load.Blocks)
            .GroupBy(static block => block.Block.Request.Caller)
            .Select(static group => new CallerResult(
                group.Key,
                group.Count(),
                group.Sum(static block => (long)block.Block.Size),
                group.Sum(static block => (long)NamedBytes(block))))
            .OrderByDescending(static caller => caller.Bytes - caller.Named)
            .ThenBy(static caller => caller.Caller),
    ];

    private static LoadResult Describe(LoadNaming load) => new(
        load.Segment,
        load.Load.Key.Scene,
        load.Load.Counter,
        [.. load.Blocks.Select(static block => new BlockResult(
            block.Block.Op,
            block.Block.Request.Caller,
            block.Block.Address,
            block.Block.Size,
            block.Block.Request.Layer?.Archive,
            block.Block.Request.Layer?.Layer,
            Kind(block.First),
            block.Bytes.OrderBy(static depth => depth.Key).ToDictionary(static depth => Label(depth.Key), static depth => depth.Value)))]);

    private sealed record BlocksResult(string Run, IReadOnlyList<LoadResult> Loads, IReadOnlyList<CallerResult> Callers);

    private sealed record LoadResult(int Segment, string Scene, int Counter, IReadOnlyList<BlockResult> Blocks);

    private sealed record BlockResult(int Op, uint Caller, uint Address, uint Size, string? Archive, int? Layer, string Kind, IReadOnlyDictionary<string, uint> Bytes);

    private sealed record CallerResult(uint Caller, int Blocks, long Bytes, long Named);
}
