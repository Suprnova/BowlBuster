using BowlBuster.Chains;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Replay;
using BowlBuster.Simulation;
using BowlBuster.Tests.Recordings;

namespace BowlBuster.Tests.Simulation;

public class RecordingLibraryTests
{
    private static readonly LoadKey OriginKey = new("ORIG", Costumes.None);

    internal static ValidatedRecording Validated(Recording recording) =>
        new ReplayValidator(PlatformProfile.XboxNtscU).Validate(recording).Recording!;

    private static ValidatedRecording Recorded(string run, int counter, int leaks = 0) =>
        Validated(new ScriptedGame(ScriptedScenes.StartAfterLeaks(leaks), run).Run(ScriptedScenes.Origin, counter).Recording);

    [Fact]
    public void Find_SeveralRecordings_OrdersByLoadThenRecordingThenSegment()
    {
        ValidatedRecording resumed = Validated(new ScriptedGame(ScriptedScenes.OriginStart, "b")
            .Run(ScriptedScenes.Origin, 3)
            .BeginSegment(ScriptedScenes.OriginStart)
            .Run(ScriptedScenes.Origin, 3)
            .Recording);
        RecordingLibrary library = new([Recorded("c", 5, 2), resumed, Recorded("a", 3)]);

        IReadOnlyList<LoadSource> found = library.Find(OriginKey);

        Assert.Equal(
            [("a", 0, 2), ("b", 0, 2), ("b", 1, 2), ("c", 0, 4)],
            found.Select(static source => (source.RecordingId, source.Segment, source.Number.Value)));
    }

    [Fact]
    public void Find_UnknownKey_IsEmpty() =>
        Assert.Empty(new RecordingLibrary([Recorded("a", 3)]).Find(new LoadKey("NONE", Costumes.None)));

    [Fact]
    public void Find_OtherCostumes_IsAnotherKey()
    {
        RecordingLibrary library = new([Recorded("a", 3)]);

        Assert.Empty(library.Find(new LoadKey("ORIG", new Costumes("Mermaid Man", null))));
    }

    [Fact]
    public void Find_BootScene_IsNeverOffered()
    {
        RecordingLibrary library = new([Recorded("a", 1)]);

        Assert.Empty(library.Find(OriginKey));
    }

    [Fact]
    public void Find_LoadWithNoRequests_IsNeverOffered()
    {
        ValidatedRecording empty = Validated(new ScriptedGame(ScriptedScenes.OriginStart).Run(new Scene("ORIG", []), 3).Recording);

        Assert.Empty(new RecordingLibrary([empty]).Find(OriginKey));
    }
}
