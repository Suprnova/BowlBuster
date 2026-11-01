using BowlBuster.Chains;
using BowlBuster.Landings;
using BowlBuster.Loads;
using BowlBuster.Memory;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Replay;
using BowlBuster.Simulation;
using BowlBuster.Tests.Recordings;

namespace BowlBuster.Tests.Simulation;

public class ChainSimulatorTests
{
    private const int OriginRecordedAt = 2;
    private const int TargetRecordedAt = 3;

    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;

    private static readonly LoadKey OriginKey = new("ORIG", Costumes.None);
    private static readonly LoadKey TargetKey = new("TARG", Costumes.None);
    private static readonly LoadKey SecondOriginKey = new("ORI2", Costumes.None);

    private static readonly Scene SecondOrigin = ScriptedScenes.Origin with { Name = "ORI2" };

    private readonly ChainSimulator simulator;

    public ChainSimulatorTests() => simulator = Simulator(Standard());

    private static ChainSimulator Simulator(IEnumerable<ValidatedRecording> recordings, PlatformProfile? profile = null) =>
        new(profile ?? Platform, new RecordingLibrary(recordings));

    private static ValidatedRecording Recorded(Scene scene, int load, HeapSnapshot start, Costumes? costumes = null, string? run = null) =>
        RecordingLibraryTests.Validated(new ScriptedGame(start, run ?? scene.Name).Run(scene, load + 1, costumes).Recording);

    private static ValidatedRecording[] Standard() =>
    [
        Recorded(ScriptedScenes.Origin, OriginRecordedAt, ScriptedScenes.OriginStart),
        Recorded(ScriptedScenes.Target, TargetRecordedAt, ScriptedScenes.TargetStart),
        Recorded(SecondOrigin, OriginRecordedAt, ScriptedScenes.OriginStart),
    ];

    private static Scene Without<TStep>(Scene scene, string name)
        where TStep : Step =>
        new(name, [.. scene.Steps.Where(static step => step is not TStep)]);

    private static Scene CutAtTheDraw(Scene scene, string name) =>
        new(name, [.. scene.Steps.TakeWhile(static step => step is not CutoffHere), new CutoffHere()]);

    private static ChainPlan Plan(int firstLoad, params LoadKey[] loads) => new(new LoadNumber(firstLoad), loads);

    private static uint? SphereAddress(SimulatedLoad load) => load.Sphere?.Address;

    private static string Same(string level) => level;

    [Theory]
    [InlineData(2, 0x73B17Cu)]
    [InlineData(3, 0x73B43Cu)]
    [InlineData(4, 0x73B73Cu)]
    [InlineData(5, 0x73B9FCu)]
    [InlineData(6, 0x73BCBCu)]
    [InlineData(7, 0x73BF7Cu)]
    public void Simulate_OriginAtEachLoad_ShiftsTheSphereByExtraLeaks(int load, uint expected)
    {
        ChainResult result = simulator.Simulate(Plan(load, OriginKey));

        SimulatedLoad origin = Assert.Single(result.Loads);
        Assert.Equal(new SphereAssignment(0, expected), origin.Sphere);
        Assert.Equal(LoadStatus.SetsSphere, origin.Status);
    }

    [Fact]
    public void Simulate_TwoRecordingsOfTheOrigin_ShiftsFromTheLatestAtOrBeforeTheLoad()
    {
        ChainSimulator chooser = Simulator(
        [
            Recorded(ScriptedScenes.Origin, 2, ScriptedScenes.OriginStart),
            Recorded(ScriptedScenes.Origin, 4, ScriptedScenes.StartAfterLeaks(2)),
        ]);

        ChainResult result = chooser.Simulate(Plan(5, OriginKey));

        SimulatedLoad origin = Assert.Single(result.Loads);
        Assert.Equal(new LoadNumber(4), origin.Source.Number);
        Assert.Equal(0x73B9FCu, SphereAddress(origin));
    }

    [Fact]
    public void Simulate_LaterRecordingOfALoadAfterTheFirst_IsUsedWithNoShift()
    {
        ChainSimulator later = Simulator(
        [
            Recorded(ScriptedScenes.Origin, OriginRecordedAt, ScriptedScenes.OriginStart),
            Recorded(ScriptedScenes.Target, 9, ScriptedScenes.TargetStart),
        ]);

        ChainResult result = later.Simulate(Plan(OriginRecordedAt, OriginKey, TargetKey));

        Assert.True(result.IsComplete);
        Assert.Equal(new LoadNumber(9), result.Loads[1].Source.Number);
    }

    [Fact]
    public void Simulate_FirstLoadEarlierThanItsRecording_IsRefused()
    {
        ChainResult result = simulator.Simulate(Plan(1, OriginKey, TargetKey));

        Assert.Equal(new CaptureRequest(OriginKey, new LoadNumber(1)), Assert.Single(result.Missing));
        Assert.Empty(result.Loads);
        Assert.False(result.IsComplete);
    }

    [Fact]
    public void Simulate_TwoLoadsWithNoRecording_ListsBothAndSimulatesNothing()
    {
        LoadKey none = new("NONE", Costumes.None);
        LoadKey gone = new("GONE", Costumes.None);

        ChainResult result = simulator.Simulate(Plan(OriginRecordedAt, OriginKey, none, TargetKey, gone));

        Assert.Equal([new CaptureRequest(none, new LoadNumber(3)), new CaptureRequest(gone, new LoadNumber(5))], result.Missing);
        Assert.Empty(result.Loads);
    }

    [Fact]
    public void Simulate_CostumesWithNoRecordingOfTheirOwn_IsRefused()
    {
        LoadKey mermaid = new("ORIG", new Costumes("Mermaid Man", null));

        ChainResult result = simulator.Simulate(Plan(OriginRecordedAt, mermaid));

        Assert.Equal(mermaid, Assert.Single(result.Missing).Key);
    }

    [Fact]
    public void Simulate_CostumedRecording_IsUsedForItsOwnKey()
    {
        Costumes mermaid = new("Mermaid Man", null);
        ChainSimulator costumed = Simulator([Recorded(ScriptedScenes.Origin, OriginRecordedAt, ScriptedScenes.OriginStart, mermaid)]);

        ChainResult result = costumed.Simulate(Plan(OriginRecordedAt, new LoadKey("ORIG", mermaid)));

        Assert.True(result.IsComplete);
    }

    [Fact]
    public void Simulate_LoadBeforeTheOrigin_HasNoSphere()
    {
        ChainResult result = simulator.Simulate(Plan(TargetRecordedAt, TargetKey, OriginKey, TargetKey));

        Assert.Equal([LoadStatus.BeforeSphere, LoadStatus.SetsSphere, LoadStatus.Landed], result.Loads.Select(static load => load.Status));
        Assert.Null(result.Loads[0].Sphere);
        Assert.Equal(1, result.Loads[2].Sphere?.Position);
    }

    [Fact]
    public void Simulate_LaterLoadSettingTheSphere_TakesOver()
    {
        ChainResult result = simulator.Simulate(Plan(OriginRecordedAt, OriginKey, SecondOriginKey, TargetKey));

        SimulatedLoad last = result.Loads[2];
        Assert.Equal(LoadStatus.Landed, last.Status);
        Assert.Equal(1, last.Sphere?.Position);
        Assert.NotEqual(SphereAddress(result.Loads[0]), SphereAddress(last));
    }

    [Fact]
    public void Simulate_SphereAllocationInALoadWithNoCutoff_StillSetsTheSphere()
    {
        Scene dark = Without<CutoffHere>(ScriptedScenes.Origin, "DARK");
        ChainSimulator simulation = Simulator([Recorded(dark, OriginRecordedAt, ScriptedScenes.OriginStart)]);

        ChainResult result = simulation.Simulate(Plan(OriginRecordedAt, new LoadKey("DARK", Costumes.None)));

        Assert.Equal(LoadStatus.SetsSphere, Assert.Single(result.Loads).Status);
    }

    [Fact]
    public void Simulate_LoadWithNoCutoffAfterTheOrigin_HasNoLandingAndKeepsTheSphere()
    {
        Scene dark = Without<CutoffHere>(ScriptedScenes.Target, "DARK");
        ChainSimulator simulation = Simulator([.. Standard(), Recorded(dark, TargetRecordedAt, ScriptedScenes.TargetStart)]);

        ChainResult result = simulation.Simulate(Plan(OriginRecordedAt, OriginKey, new LoadKey("DARK", Costumes.None), TargetKey));

        Assert.Equal([LoadStatus.SetsSphere, LoadStatus.NoCutoff, LoadStatus.Landed], result.Loads.Select(static load => load.Status));
        Assert.Equal(SphereAddress(result.Loads[0]), SphereAddress(result.Loads[2]));
    }

    [Fact]
    public void Simulate_LoadCutBeforeItsExit_LeavesTheSameHeapAsAWholeOne()
    {
        Scene cut = CutAtTheDraw(ScriptedScenes.Target, "CUTS");
        ChainSimulator simulation = Simulator([.. Standard(), Recorded(cut, TargetRecordedAt, ScriptedScenes.TargetStart)]);

        ChainResult whole = simulation.Simulate(Plan(OriginRecordedAt, OriginKey, TargetKey, SecondOriginKey));
        ChainResult cutShort = simulation.Simulate(Plan(OriginRecordedAt, OriginKey, new LoadKey("CUTS", Costumes.None), SecondOriginKey));

        Assert.False(cutShort.Loads[1].Source.Load.Heap.ReachedExit);
        Assert.Equal(SphereAddress(whole.Loads[2]), SphereAddress(cutShort.Loads[2]));
    }

    [Fact]
    public void Simulate_LoadsFromTwoRecordings_LandAsOneRecordingDoes()
    {
        ChainSimulator oneRun = Simulator(
        [
            RecordingLibraryTests.Validated(new ScriptedGame(ScriptedScenes.OriginStart)
                .Run(ScriptedScenes.Origin, OriginRecordedAt + 1)
                .Run(ScriptedScenes.Target, TargetRecordedAt + 1)
                .Run(SecondOrigin, TargetRecordedAt + 2)
                .Recording),
        ]);
        ChainPlan plan = Plan(OriginRecordedAt, OriginKey, TargetKey, SecondOriginKey);

        ChainResult together = oneRun.Simulate(plan);
        ChainResult apart = simulator.Simulate(plan);

        Assert.Equal(together.Loads.Select(SphereAddress), apart.Loads.Select(SphereAddress));
        Assert.Equal(["ORIG", "TARG", "ORI2"], apart.Loads.Select(static load => load.Source.RecordingId));
    }

    [Fact]
    public void Simulate_HeapTooSmallForALaterLoad_StopsThereWithTheLoadsSoFar()
    {
        PlatformProfile tight = Platform with { Heap0 = Platform.Heap0 with { Size = 0x1D868C } };
        ChainSimulator simulation = Simulator(Standard(), tight);

        ChainResult result = simulation.Simulate(Plan(OriginRecordedAt, OriginKey, TargetKey));

        Assert.Equal(new HeapExhaustion(1, 8), result.Exhausted);
        Assert.Equal("ORIG", Assert.Single(result.Loads).Source.Load.Key.Scene);
        Assert.False(result.IsComplete);
    }

    [Fact]
    public void Simulate_LoadsNumberedFromTheFirst_CountUpAndKeepTheirPositions()
    {
        ChainResult result = simulator.Simulate(Plan(5, OriginKey, TargetKey, TargetKey));

        Assert.Equal([5, 6, 7], result.Loads.Select(static load => load.Load.Value));
        Assert.Equal([0, 1, 2], result.Loads.Select(static load => load.Position));
    }

    [Fact]
    public void Simulate_RecordedLoadAtAnotherDepth_Throws()
    {
        HeapSnapshot deeper = ScriptedScenes.TargetStart with { States = [.. ScriptedScenes.TargetStart.States, ScriptedScenes.TargetStart.States[^1]] };
        Scene deep = new("DEEP", [new Alloc(0x20, 0, ScriptedScenes.PlaySite)]);
        ChainSimulator simulation = Simulator([.. Standard(), Recorded(deep, TargetRecordedAt, deeper)]);

        Assert.Throws<InvalidOperationException>(() => simulation.Simulate(Plan(OriginRecordedAt, OriginKey, new LoadKey("DEEP", Costumes.None))));
    }

    [Fact]
    public void Simulate_NoLoads_Throws() =>
        Assert.Throws<ArgumentException>(() => simulator.Simulate(new ChainPlan(new LoadNumber(1), [])));

    [Theory]
    [InlineData(Phase.Third, 2)]
    [InlineData(Phase.Fourth, 3)]
    [InlineData(Phase.First, 4)]
    [InlineData(Phase.Second, 5)]
    public void SimulatePhases_NoPhasesWritten_RunsEveryPhaseFromTheEarliestOriginThatReachesIt(Phase phase, int expectedOrigin)
    {
        IReadOnlyList<PhaseResult> results = simulator.SimulatePhases(Chain.Parse("ORIG > TARG"), Same);

        PhaseResult result = Assert.Single(results, found => found.TargetPhase == phase);
        Assert.Equal(new LoadNumber(expectedOrigin), result.OriginLoad);
        Assert.True(result.Result.IsComplete);
        Assert.Equal(phase, result.Result.Loads[^1].Load.Phase);
    }

    [Fact]
    public void SimulatePhases_PhasesWritten_RunsOnlyThose()
    {
        IReadOnlyList<PhaseResult> results = simulator.SimulatePhases(Chain.Parse("ORIG > TARG [target: 1st or 4th]"), Same);

        Assert.Equal([Phase.First, Phase.Fourth], results.Select(static result => result.TargetPhase));
        Assert.Equal([4, 3], results.Select(static result => result.OriginLoad?.Value));
    }

    [Fact]
    public void SimulatePhases_NoRecordingOfTheOrigin_RefusesEveryPhaseAtAnyLoad()
    {
        IReadOnlyList<PhaseResult> results = simulator.SimulatePhases(Chain.Parse("NONE > TARG"), Same);

        Assert.Equal(4, results.Count);
        Assert.All(results, static result =>
        {
            Assert.Null(result.OriginLoad);
            Assert.Equal(new CaptureRequest(new LoadKey("NONE", Costumes.None), null), Assert.Single(result.Result.Missing));
        });
    }

    [Fact]
    public void SimulatePhases_FullChain_Throws() =>
        Assert.Throws<ArgumentException>(() => simulator.SimulatePhases(Chain.Parse("[load] > ORIG > TARG"), Same));
}
