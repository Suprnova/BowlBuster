using BowlBuster.Chains;
using BowlBuster.Landings;
using BowlBuster.Loads;
using BowlBuster.Memory;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Replay;
using BowlBuster.Simulation;
using BowlBuster.Tests.Recordings;
using BowlBuster.Tests.Simulation;

namespace BowlBuster.Tests.Landings;

public class LandingTests
{
    private const int OriginRecordedAt = 2;
    private const int LaterRecordedAt = 3;
    private const int TargetLayerOp = 8;
    private const int FillerPlayOp = 3;

    private const uint ScaleWord = 0x40833333;

    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;

    private static readonly LoadKey OriginKey = new("ORIG", Costumes.None);
    private static readonly LoadKey TargetKey = new("TARG", Costumes.None);
    private static readonly LoadKey FillerKey = new("FILL", Costumes.None);

    private readonly ChainSimulator simulator;

    public LandingTests() => simulator = new ChainSimulator(
        Platform,
        new RecordingLibrary(
        [
            Recorded(ScriptedScenes.Origin, OriginRecordedAt, ScriptedScenes.OriginStart),
            Recorded(ScriptedScenes.Target, LaterRecordedAt, ScriptedScenes.TargetStart),
            Recorded(ScriptedScenes.Filler, LaterRecordedAt, ScriptedScenes.TargetStart),
        ]));

    private static ValidatedRecording Recorded(Scene scene, int load, HeapSnapshot start) =>
        RecordingLibraryTests.Validated(new ScriptedGame(start, scene.Name).Run(scene, load + 1).Recording);

    private ChainResult Simulate(int firstLoad, params LoadKey[] loads) => simulator.Simulate(new ChainPlan(new LoadNumber(firstLoad), loads));

    private Landing LandingOf(int position, int firstLoad, params LoadKey[] loads) =>
        Assert.IsType<Landing>(Simulate(firstLoad, loads).Loads[position].Landing);

    private static LandingWord At(Landing landing, uint offset) => Assert.NotNull(landing.WordAt(offset));

    [Fact]
    public void Footprint_Xbox_IsTheFourWritesThenTheRenderPathsReads()
    {
        FootprintWord[] expected =
        [
            new(0x38, 4, 0), new(0x58, 4, ScaleWord), new(0x5C, 4, ScaleWord), new(0x60, 4, ScaleWord),
            new(0x10, 4, null), new(0x14, 4, null), new(0x2C, 4, null), new(0x30, 4, null), new(0x34, 4, null),
            new(0x3C, 4, null), new(0x4C, 2, null), new(0x4E, 1, null), new(0x54, 4, null),
            new(0x64, 4, null), new(0x68, 4, null), new(0x6C, 4, null), new(0x70, 4, null), new(0x74, 4, null), new(0x78, 4, null),
        ];

        Assert.Equal(expected, Platform.Footprint.Words);
    }

    [Fact]
    public void Landing_TargetOnItsRecordedLoad_NamesTheSphereAndTheHeapAtTheCutoff()
    {
        Landing landing = LandingOf(1, OriginRecordedAt, OriginKey, TargetKey);

        Assert.Equal(new SphereAssignment(0, 0x73B17C), landing.Sphere);
        Assert.Equal(0x6E6F30u, landing.PlayerEntity);
        Assert.Equal(new LandingHeap(0x79876C, 0x79876C, 4), landing.Heap);
    }

    [Theory]
    [InlineData(0x38u, 0x73B1B4u, 0x2AB4u)]
    [InlineData(0x58u, 0x73B1D4u, 0x2AD4u)]
    [InlineData(0x5Cu, 0x73B1D8u, 0x2AD8u)]
    [InlineData(0x60u, 0x73B1DCu, 0x2ADCu)]
    public void Landing_TargetOnItsRecordedLoad_PutsEachWriteInTheTargetsLayer(uint wordOffset, uint address, uint offset)
    {
        Landing landing = LandingOf(1, OriginRecordedAt, OriginKey, TargetKey);

        LandingWord word = At(landing, wordOffset);

        Assert.Equal(address, word.Address);
        Assert.Equal(RegionKind.Block, word.Region.Kind);
        Assert.Equal(1, word.Region.Block?.Position);
        Assert.Equal(TargetLayerOp, word.Region.Block?.Op);
        Assert.Equal(offset, word.Region.Offset);
    }

    [Fact]
    public void Landing_FourthLoad_FallsSixtyFourBytesEarlier()
    {
        Landing landing = LandingOf(1, 3, OriginKey, TargetKey);

        Assert.Equal(0x73B43Cu, landing.Sphere.Address);
        Assert.Equal(0x2A94u, At(landing, 0x58).Region.Offset);
    }

    [Fact]
    public void Landing_Word_ComesFromTheFootprint()
    {
        Landing landing = LandingOf(1, OriginRecordedAt, OriginKey, TargetKey);

        Assert.Equal(Platform.Footprint.Words, landing.Words.Select(static word => word.Word));
    }

    [Fact]
    public void WordAt_TheFlags_IsTheTwoByteRead()
    {
        Landing landing = LandingOf(1, OriginRecordedAt, OriginKey, TargetKey);

        Assert.Equal(new FootprintWord(0x4C, 2, null), At(landing, 0x4C).Word);
    }

    [Fact]
    public void WordAt_AnOffsetOutsideTheFootprint_IsNull()
    {
        Landing landing = LandingOf(1, OriginRecordedAt, OriginKey, TargetKey);

        Assert.Null(landing.WordAt(0x40));
    }

    [Fact]
    public void Landing_HeapThatEndsBelowTheSphereAtTheCutoff_IsAboveItEvenThoughPlayReachesPastLater()
    {
        Landing landing = LandingOf(1, OriginRecordedAt, OriginKey, FillerKey);

        Assert.All(landing.Words, static word => Assert.Equal(new LandingRegion(RegionKind.AboveHeap, null, 0), word.Region));
        Assert.True(landing.Sphere.Address >= landing.Heap.Top);
    }

    [Fact]
    public void Landing_AboveTheHeapPastAnEarlierFillersPlayBlock_NamesThatBlock()
    {
        Landing landing = LandingOf(2, OriginRecordedAt, OriginKey, FillerKey, FillerKey);

        Assert.All(landing.Words, static word =>
        {
            Assert.Equal(RegionKind.AboveHeap, word.Region.Kind);
            Assert.Equal(1, word.Region.Block?.Position);
            Assert.Equal(FillerPlayOp, word.Region.Block?.Op);
        });
    }

    [Fact]
    public void Landing_AboveTheHeapPastAnEarlierTarget_NamesItsLayer()
    {
        Landing landing = LandingOf(2, OriginRecordedAt, OriginKey, TargetKey, FillerKey);

        Assert.All(landing.Words, static word =>
        {
            Assert.Equal(RegionKind.AboveHeap, word.Region.Kind);
            Assert.Equal(1, word.Region.Block?.Position);
            Assert.Equal(TargetLayerOp, word.Region.Block?.Op);
        });
    }

    [Fact]
    public void Landing_TwoTargetsInARow_EachLandsAtItsOwnOffset()
    {
        ChainResult result = Simulate(OriginRecordedAt, OriginKey, TargetKey, TargetKey);

        Assert.Equal(0x2AD4u, At(result.Loads[1].Landing!, 0x58).Region.Offset);
        Assert.Equal(0x27D4u, At(result.Loads[2].Landing!, 0x58).Region.Offset);
    }

    [Fact]
    public void Landing_LoadsThatDoNotLand_HaveNone()
    {
        ChainResult result = Simulate(LaterRecordedAt, TargetKey, OriginKey, TargetKey);

        Assert.Null(result.Loads[0].Landing);
        Assert.Null(result.Loads[1].Landing);
        Assert.NotNull(result.Loads[2].Landing);
    }

    [Fact]
    public void Landing_LoadWithNoCutoff_HasNone()
    {
        Scene dark = new("DARK", [.. ScriptedScenes.Target.Steps.Where(static step => step is not CutoffHere)]);
        ChainSimulator simulation = new(
            Platform,
            new RecordingLibrary(
            [
                Recorded(ScriptedScenes.Origin, OriginRecordedAt, ScriptedScenes.OriginStart),
                Recorded(dark, LaterRecordedAt, ScriptedScenes.TargetStart),
            ]));

        ChainResult result = simulation.Simulate(new ChainPlan(new LoadNumber(OriginRecordedAt), [OriginKey, new LoadKey("DARK", Costumes.None)]));

        Assert.Equal(LoadStatus.NoCutoff, result.Loads[1].Status);
        Assert.Null(result.Loads[1].Landing);
    }

    [Fact]
    public void Landing_BlocksAfterTheCutoff_StillGrowTheHeapForTheNextLoad()
    {
        Landing first = LandingOf(1, OriginRecordedAt, OriginKey, FillerKey);
        Landing second = LandingOf(2, OriginRecordedAt, OriginKey, FillerKey, FillerKey);

        Assert.Equal(first.PlayerEntity + 720, second.PlayerEntity);
    }

    [Fact]
    public void FindFrom_NoBlockFromThatSite_IsNull()
    {
        BlockTracker tracker = new(Platform.Heap0);
        tracker.BeginLoad();

        Assert.Null(tracker.FindFrom(Platform.Sites.PlayerEntity));
    }
}
