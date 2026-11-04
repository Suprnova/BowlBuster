using BowlBuster.Cli;
using BowlBuster.Memory;
using BowlBuster.Recordings;
using BowlBuster.Tests.Recordings;
using System.Globalization;
using System.Text.Json.Nodes;

namespace BowlBuster.Tests.Cli;

public sealed class PlaceCommandTests : IDisposable
{
    private const int EntityOp = 0;

    private readonly StringWriter output = new();
    private readonly StringWriter error = new();
    private readonly DirectoryInfo scratch = Directory.CreateTempSubdirectory("bowlbuster-place-");

    public void Dispose()
    {
        output.Dispose();
        error.Dispose();
        scratch.Delete(recursive: true);
    }

    private static ScriptedGame Origin(string? capture = null) => new ScriptedGame(ScriptedScenes.OriginStart).Run(ScriptedScenes.Origin, 3, capture: capture);

    private static uint EntityAddress(ScriptedGame game) => ((AllocRequest)game.Recording.Segments[0].Loads[0].Heap.Requests[EntityOp]).Address;

    private static string Hex(uint value) => $"0x{value.ToString("x8", CultureInfo.InvariantCulture)}";

    private string HeapFile(HeapSnapshot heap, string? text = null)
    {
        JsonArray states = [];
        foreach (HeapState state in heap.States)
            states.Add(new JsonObject { ["cursor"] = state.Cursor, ["blocks"] = state.BlockCount, ["used"] = state.Used, ["wasted"] = 0 });

        JsonObject document = new()
        {
            ["depth"] = heap.Depth,
            ["states"] = states,
            ["last_block"] = heap.LastBlock is { } block ? new JsonObject { ["address"] = block.Address, ["size"] = block.Size } : null,
        };

        string path = Path.Combine(scratch.FullName, "heap.json");
        File.WriteAllText(path, text ?? document.ToJsonString());
        return path;
    }

    private int Place(string recording, string heap, params string[] more) =>
        CommandLineApp.Run(["place", "--recording", recording, "--load", "3", "--heap", heap, "--op", EntityOp.ToString(CultureInfo.InvariantCulture), .. more], output, error);

    [Fact]
    public void Place_Placed_PrintsTheSphereAndExitsZero()
    {
        ScriptedGame game = Origin();
        using ScriptedRecordingFolder folder = new(game);

        int exitCode = Place(folder.Path, HeapFile(ScriptedScenes.OriginStart), "--delta", "16");

        Assert.Equal(CommandLineApp.Success, exitCode);
        Assert.Equal($"{Hex(EntityAddress(game) + 16)}{Environment.NewLine}", output.ToString());
        Assert.Equal("", error.ToString());
    }

    [Fact]
    public void Place_NegativeDelta_IsReadAsANumber()
    {
        ScriptedGame game = Origin();
        using ScriptedRecordingFolder folder = new(game);

        int exitCode = Place(folder.Path, HeapFile(ScriptedScenes.OriginStart), "--delta", "-24");

        Assert.Equal(CommandLineApp.Success, exitCode);
        Assert.Equal($"{Hex(EntityAddress(game) - 24)}{Environment.NewLine}", output.ToString());
    }

    [Fact]
    public void Place_Top_PrintsTheCursorAndDepthAtTheCutoffOnASecondLine()
    {
        ScriptedGame game = Origin("0-3-cutoff");
        using ScriptedRecordingFolder folder = new(game);

        Place(folder.Path, HeapFile(ScriptedScenes.OriginStart), "--delta", "0", "--top");

        Assert.Equal([Hex(EntityAddress(game)), $"{Hex(game.CaptureTops["0-3-cutoff"])} 4"], output.ToString().Split(Environment.NewLine, StringSplitOptions.RemoveEmptyEntries));
    }

    [Fact]
    public void Place_OpPastTheList_ExitsRejectedWithNothingOnStdout()
    {
        using ScriptedRecordingFolder folder = new(Origin());

        int exitCode = CommandLineApp.Run(["place", "--recording", folder.Path, "--load", "3", "--heap", HeapFile(ScriptedScenes.OriginStart), "--op", "99", "--delta", "0"], output, error);

        Assert.Equal(CommandLineApp.Rejected, exitCode);
        Assert.Equal("", output.ToString());
        Assert.Contains("no op 99", error.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public void Place_RecordingThatDoesNotExist_ExitsUnreadable()
    {
        int exitCode = Place(Path.Combine(scratch.FullName, "missing"), HeapFile(ScriptedScenes.OriginStart), "--delta", "0");

        Assert.Equal(CommandLineApp.Unreadable, exitCode);
        Assert.Equal("", output.ToString());
    }

    [Fact]
    public void Place_IncompleteRecording_ExitsUnreadable()
    {
        using ScriptedRecordingFolder folder = new(Origin(), complete: false);

        int exitCode = Place(folder.Path, HeapFile(ScriptedScenes.OriginStart), "--delta", "0");

        Assert.Equal(CommandLineApp.Unreadable, exitCode);
    }

    [Fact]
    public void Place_RecordingReplayRejects_ExitsUnreadableWithTheMismatch()
    {
        using ScriptedRecordingFolder folder = new(Origin(), changeEvent: static line =>
        {
            if (line["event"]?.GetValue<string>() is "alloc") line["address"] = line["address"]!.GetValue<uint>() + 16;
            return line;
        });

        int exitCode = Place(folder.Path, HeapFile(ScriptedScenes.OriginStart), "--delta", "0");

        Assert.Equal(CommandLineApp.Unreadable, exitCode);
        Assert.Contains("ReturnedAddress", error.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public void Place_LoadNoSegmentHolds_ExitsUnreadable()
    {
        using ScriptedRecordingFolder folder = new(Origin());

        int exitCode = CommandLineApp.Run(["place", "--recording", folder.Path, "--load", "8", "--heap", HeapFile(ScriptedScenes.OriginStart), "--op", "0", "--delta", "0"], output, error);

        Assert.Equal(CommandLineApp.Unreadable, exitCode);
        Assert.Contains("No segment holds load 8", error.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public void Place_LoadTwoSegmentsHoldWithoutASegment_ExitsUsageNamingThem()
    {
        using ScriptedRecordingFolder folder = new(Origin().BeginSegment(ScriptedScenes.StartAfterLeaks(1)).Run(ScriptedScenes.Origin, 3));

        int exitCode = Place(folder.Path, HeapFile(ScriptedScenes.OriginStart), "--delta", "0");

        Assert.Equal(CommandLineApp.Usage, exitCode);
        Assert.Contains("Segments 0, 1 each hold load 3", error.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public void Place_LoadTwoSegmentsHoldWithASegment_Places()
    {
        using ScriptedRecordingFolder folder = new(Origin().BeginSegment(ScriptedScenes.StartAfterLeaks(1)).Run(ScriptedScenes.Origin, 3));

        int exitCode = Place(folder.Path, HeapFile(ScriptedScenes.OriginStart), "--delta", "0", "--segment", "1");

        Assert.Equal(CommandLineApp.Success, exitCode);
    }

    [Theory]
    [InlineData("{")]
    [InlineData("{\"depth\": 0}")]
    public void Place_MalformedHeapFile_ExitsUsage(string heap)
    {
        using ScriptedRecordingFolder folder = new(Origin());

        int exitCode = Place(folder.Path, HeapFile(ScriptedScenes.OriginStart, heap), "--delta", "0");

        Assert.Equal(CommandLineApp.Usage, exitCode);
        Assert.Equal("", output.ToString());
        Assert.Contains("Cannot read the heap state", error.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public void Place_MissingOption_ExitsUsage()
    {
        int exitCode = CommandLineApp.Run(["place", "--load", "3"], output, error);

        Assert.Equal(CommandLineApp.Usage, exitCode);
        Assert.Equal("", output.ToString());
    }
}
