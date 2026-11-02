using BowlBuster.Cli;
using BowlBuster.Tests.Recordings;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace BowlBuster.Tests.Cli;

public sealed class ValidateCommandTests : IDisposable
{
    private readonly StringWriter output = new();
    private readonly StringWriter error = new();

    public void Dispose()
    {
        output.Dispose();
        error.Dispose();
    }

    private int Run(params string[] args) => CommandLineApp.Run(args, output, error);

    private static JsonObject WithWrongAddress(JsonObject line)
    {
        if (line["event"]?.GetValue<string>() is "alloc" && line["heap"]?.GetValue<int>() is 0)
            line["address"] = line["address"]!.GetValue<uint>() + 16;

        return line;
    }

    [Fact]
    public void Validate_AcceptedRecording_ExitsZeroAndListsItsLoads()
    {
        using ScriptedRecordingFolder folder = new(ScriptedRecordingFolder.TwoLoads());

        int exitCode = Run("recordings", "validate", folder.Path);

        Assert.Equal(CommandLineApp.Success, exitCode);
        Assert.Contains("Accepted synthetic-1 (xbox): 1 segment(s), 2 load(s).", output.ToString(), StringComparison.Ordinal);
        Assert.Contains("ORIG  counter 3  load 2", output.ToString(), StringComparison.Ordinal);
        Assert.Equal("", error.ToString());
    }

    [Fact]
    public void Validate_AcceptedRecordingAsJson_PrintsTheTypedResult()
    {
        using ScriptedRecordingFolder folder = new(ScriptedRecordingFolder.TwoLoads());

        int exitCode = Run("recordings", "validate", folder.Path, "--json");

        JsonNode result = JsonNode.Parse(output.ToString())!;
        Assert.Equal(CommandLineApp.Success, exitCode);
        Assert.True(result["accepted"]!.GetValue<bool>());
        Assert.Equal("synthetic-1", result["run"]!.GetValue<string>());
        Assert.Equal(["ORIG", "TARG"], result["segments"]![0]!["loads"]!.AsArray().Select(static load => load!["scene"]!.GetValue<string>()));
    }

    [Fact]
    public void Validate_RecordingWithAWrongAddress_ExitsRejectedWithTheMismatchOnStderr()
    {
        using ScriptedRecordingFolder folder = new(ScriptedRecordingFolder.TwoLoads(), changeEvent: WithWrongAddress);

        int exitCode = Run("recordings", "validate", folder.Path);

        Assert.Equal(CommandLineApp.Rejected, exitCode);
        Assert.Contains("Rejected synthetic-1: ORIG (segment 0, counter 3), op 0: ReturnedAddress", error.ToString(), StringComparison.Ordinal);
        Assert.Equal("", output.ToString());
    }

    [Fact]
    public void Validate_RejectedRecordingAsJson_PrintsTheMismatchAndExitsRejected()
    {
        using ScriptedRecordingFolder folder = new(ScriptedRecordingFolder.TwoLoads(), changeEvent: WithWrongAddress);

        int exitCode = Run("recordings", "validate", folder.Path, "--json");

        JsonNode mismatch = JsonNode.Parse(output.ToString())!["mismatch"]!;
        Assert.Equal(CommandLineApp.Rejected, exitCode);
        Assert.Equal("ReturnedAddress", mismatch["check"]!.GetValue<string>());
        Assert.Equal(("ORIG", 3, 0), (mismatch["scene"]!.GetValue<string>(), mismatch["counter"]!.GetValue<int>(), mismatch["op"]!.GetValue<int>()));
        Assert.Equal(mismatch["recorded"]!.GetValue<uint>() - 16, mismatch["replayed"]!.GetValue<uint>());
    }

    [Fact]
    public void Validate_RecordingThatDoesNotExist_ExitsUnreadable()
    {
        int exitCode = Run("recordings", "validate", Path.Combine(AppContext.BaseDirectory, "no-such-recording"));

        Assert.Equal(CommandLineApp.Unreadable, exitCode);
        Assert.Contains("does not exist", error.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public void Validate_IncompleteRecording_ExitsUnreadableQuotingWhy()
    {
        using ScriptedRecordingFolder folder = new(ScriptedRecordingFolder.TwoLoads(), complete: false);

        int exitCode = Run("recordings", "validate", folder.Path);

        Assert.Equal(CommandLineApp.Unreadable, exitCode);
        Assert.Contains("emulator exited", error.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public void Validate_CatalogThatDoesNotExist_ExitsUnreadable()
    {
        using ScriptedRecordingFolder folder = new(ScriptedRecordingFolder.TwoLoads());

        int exitCode = Run("recordings", "validate", folder.Path, "--catalog", Path.Combine(AppContext.BaseDirectory, "no-such-catalog"));

        Assert.Equal(CommandLineApp.Unreadable, exitCode);
    }

    [Fact]
    public void Validate_AcceptedRecordingWithTheCatalog_NamesTheCostumes()
    {
        using ScriptedRecordingFolder folder = new(new ScriptedGame(ScriptedScenes.OriginStart).Run(ScriptedScenes.Origin, 3, new BowlBuster.Chains.Costumes("PLSB", null)));

        int exitCode = Run("recordings", "validate", folder.Path, "--catalog", Path.Combine(AppContext.BaseDirectory, "catalog"));

        Assert.Equal(CommandLineApp.Success, exitCode);
        Assert.Contains("Mermaid Man / -", output.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public void Validate_AcceptedRecordingWithoutACatalog_KeepsTheArchiveTags()
    {
        using ScriptedRecordingFolder folder = new(new ScriptedGame(ScriptedScenes.OriginStart).Run(ScriptedScenes.Origin, 3, new BowlBuster.Chains.Costumes("PLSB", null)));

        Run("recordings", "validate", folder.Path);

        Assert.Contains("PLSB / -", output.ToString(), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("recordings", "validate")]
    [InlineData("recordings", "validate", "somewhere", "--bogus")]
    [InlineData("recordings")]
    [InlineData("unknown")]
    public void Run_AMalformedCall_ExitsUsageWithAMessage(params string[] args)
    {
        int exitCode = Run(args);

        Assert.Equal(CommandLineApp.Usage, exitCode);
        Assert.NotEqual("", error.ToString());
        Assert.Equal("", output.ToString());
    }

    [Fact]
    public void Run_Version_PrintsTheBanner()
    {
        int exitCode = Run("--version");

        Assert.Equal(CommandLineApp.Success, exitCode);
        Assert.Equal($"{VersionBanner.For(typeof(VersionBanner).Assembly)}{Environment.NewLine}", output.ToString());
    }
}
