using BowlBuster.Cli;
using BowlBuster.Tests.Recordings;
using System.Text.Json.Nodes;
using static BowlBuster.Tests.Recordings.ScriptedScenes;

namespace BowlBuster.Tests.Cli;

public sealed class BlocksCommandTests : IDisposable
{
    private readonly StringWriter output = new();
    private readonly StringWriter error = new();

    public void Dispose()
    {
        output.Dispose();
        error.Dispose();
    }

    private int Run(params string[] args) => CommandLineApp.Run(args, output, error);

    private static ScriptedGame Captured() => new ScriptedGame(OriginStart).Run(Origin, 3).Run(Target, 4, capture: "target-cutoff");

    [Fact]
    public void Blocks_CapturedLoad_ListsItsBlocksAndTheCallers()
    {
        using ScriptedRecordingFolder folder = new(Captured());

        int exitCode = Run("recordings", "blocks", folder.Path);

        Assert.Equal(CommandLineApp.Success, exitCode);
        Assert.Contains("Blocks of synthetic-1: 1 captured cutoff(s), 0.0% named", output.ToString(), StringComparison.Ordinal);
        Assert.Contains("Segment 0  TARG  counter 4  7 block(s), 0.0% named", output.ToString(), StringComparison.Ordinal);
        Assert.Matches(@"op \d+  0x192860  0x[0-9A-F]+  size 0x60040  unknown  TARG layer 0  caller 100\.0%", output.ToString());
        Assert.Matches(@"0x192860  2 block\(s\)  0x60840 bytes  0\.0% named", output.ToString());
        Assert.Equal("", error.ToString());
    }

    [Fact]
    public void Blocks_AsJson_PrintsEveryBlockByDepth()
    {
        using ScriptedRecordingFolder folder = new(Captured());

        Run("recordings", "blocks", folder.Path, "--json");

        JsonNode load = JsonNode.Parse(output.ToString())!["loads"]![0]!;
        JsonNode layer = load["blocks"]!.AsArray().Single(static block => block!["archive"]?.GetValue<string>() == "TARG")!;
        Assert.Equal("TARG", load["scene"]!.GetValue<string>());
        Assert.Equal(0x60040u, layer["bytes"]!["caller"]!.GetValue<uint>());
    }

    [Fact]
    public void Blocks_RejectedRecording_ExitsRejected()
    {
        using ScriptedRecordingFolder folder = new(Captured(), changeEvent: static line =>
        {
            if (line["event"]?.GetValue<string>() is "alloc" && line["heap"]?.GetValue<int>() is 0)
                line["address"] = line["address"]!.GetValue<uint>() + 16;
            return line;
        });

        int exitCode = Run("recordings", "blocks", folder.Path);

        Assert.Equal(CommandLineApp.Rejected, exitCode);
        Assert.StartsWith("Rejected synthetic-1", error.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public void Blocks_DiscThatIsntADirectory_ExitsUnreadable()
    {
        using ScriptedRecordingFolder folder = new(Captured());

        int exitCode = Run("recordings", "blocks", folder.Path, "--disc", Path.Combine(folder.Path, "no-such-disc"));

        Assert.Equal(CommandLineApp.Unreadable, exitCode);
        Assert.Contains("Cannot read the disc", error.ToString(), StringComparison.Ordinal);
    }
}
