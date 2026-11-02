using BowlBuster.Catalog;
using BowlBuster.Chains;
using BowlBuster.Recordings;
using BowlBuster.Tests.Catalog;

namespace BowlBuster.Tests.Recordings;

public class RecordingDirectoryTests
{
    private static IReadOnlyList<RecordedLoad> Loads(Recording recording) => [.. recording.Segments.SelectMany(static segment => segment.Loads)];

    [Fact]
    public void Read_SyntheticRecording_ReadsEveryLoadByItsCounter()
    {
        Recording recording = RecordingDirectory.Read(SyntheticRecording.Committed, TestVocabulary.CostumesOnly);

        Assert.Equal(SyntheticRecording.RunId, recording.Id);
        Assert.Equal(["ORIG", "TARG", "TARG"], Loads(recording).Select(static load => load.Key.Scene));
        Assert.Equal([2, 3, 4], Loads(recording).Select(static load => load.Counter));
    }

    [Fact]
    public void Read_ArchiveTagsOfCostumes_BecomeTheCostumesNames()
    {
        Recording recording = RecordingDirectory.Read(SyntheticRecording.Committed, TestVocabulary.CostumesOnly);

        Assert.Equal(new Costumes("Mermaid Man", "Plain Patrick"), Loads(recording)[0].Key.Costumes);
        Assert.Equal(new Costumes("Plain Sponge", null), Loads(recording)[1].Key.Costumes);
    }

    [Fact]
    public void Read_ArchiveTagNoCostumeHas_StaysAsTheCostumesName()
    {
        Recording recording = RecordingDirectory.Read(SyntheticRecording.Committed, TestVocabulary.CostumesOnly);

        Assert.Equal(new Costumes(null, "PLPA"), Loads(recording)[2].Key.Costumes);
    }

    [Fact]
    public void Read_WithoutNames_KeepsEveryArchiveTag()
    {
        Recording recording = RecordingDirectory.Read(SyntheticRecording.Committed, Vocabulary.Empty);

        Assert.Equal(new Costumes("PLSB", "PLP1"), Loads(recording)[0].Key.Costumes);
    }

    [Fact]
    public void Read_ManifestThatIsNotComplete_ThrowsNamingTheRecording()
    {
        using SyntheticRecording recording = SyntheticRecording.CopyOfCommitted();
        string manifest = recording.FileOf("manifest.json");
        File.WriteAllText(manifest, File.ReadAllText(manifest).Replace("\"complete\": true", "\"complete\": false", StringComparison.Ordinal));

        FormatException exception = Assert.Throws<FormatException>(() => RecordingDirectory.Read(recording.Path, Vocabulary.Empty));

        Assert.Contains(recording.Path, exception.Message, StringComparison.Ordinal);
        Assert.Contains("incomplete", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Read_InterruptedRecording_QuotesTheReason()
    {
        using SyntheticRecording recording = SyntheticRecording.CopyOfCommitted();
        string manifest = recording.FileOf("manifest.json");
        File.WriteAllText(manifest, File.ReadAllText(manifest).Replace("\"complete\": true", "\"complete\": false", StringComparison.Ordinal).Replace("\"interrupted\": null", "\"interrupted\": \"emulator exited\"", StringComparison.Ordinal));

        FormatException exception = Assert.Throws<FormatException>(() => RecordingDirectory.Read(recording.Path, Vocabulary.Empty));

        Assert.Contains("emulator exited", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Read_ManifestWithoutAComplete_IsIncomplete()
    {
        using SyntheticRecording recording = SyntheticRecording.CopyOfCommitted();
        File.WriteAllText(recording.FileOf("manifest.json"), """{ "schema_version": 1, "run": "run-1" }""");

        Assert.Throws<FormatException>(() => RecordingDirectory.Read(recording.Path, Vocabulary.Empty));
    }

    [Fact]
    public void Read_MissingDirectory_ThrowsDirectoryNotFound()
    {
        string missing = Path.Combine(AppContext.BaseDirectory, "no-such-recording");

        Assert.Throws<DirectoryNotFoundException>(() => RecordingDirectory.Read(missing, Vocabulary.Empty));
    }

    [Fact]
    public void Read_DirectoryWithoutEvents_ThrowsFileNotFound()
    {
        using SyntheticRecording recording = SyntheticRecording.CopyOfCommitted();
        File.Delete(recording.FileOf("events.jsonl"));

        Assert.Throws<FileNotFoundException>(() => RecordingDirectory.Read(recording.Path, Vocabulary.Empty));
    }
}
