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

/// <summary>
/// Checks that replay reproduces the chain arithmetic. The arithmetic is written out here, independently of the library,
/// which never evaluates it: the simulator only replays requests.
/// </summary>
public class ChainArithmeticTests
{
    private const int OriginRecordedAt = 2;
    private const int LaterRecordedAt = 3;

    private const long Leak = 720;
    private const long OriginCursorAtLoadTwo = 0x6E6F18;
    private const int OriginU = 12;
    private const long SphereFromOriginAnchor = 0x5423C;
    private const long LayerFromTargetAnchor = 0x51500;

    private const uint ZeroWord = 0x38;

    private const string TargetCapture = "target-cutoff";

    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;

    private static readonly LoadKey OriginKey = new("ORIG", Costumes.None);
    private static readonly LoadKey TargetKey = new("TARG", Costumes.None);
    private static readonly LoadKey FillerKey = new("FILL", Costumes.None);

    private static readonly uint[] PrefixSizes = [0x20, 0x34];

    private readonly ChainSimulator simulator;

    public ChainArithmeticTests()
    {
        ValidatedRecording[] variants = [.. PrefixSizes.Select(static size => Recorded(WithPrefix(size), LaterRecordedAt, ScriptedScenes.TargetStart))];

        simulator = new ChainSimulator(
            Platform,
            new RecordingLibrary(
            [
                Recorded(ScriptedScenes.Origin, OriginRecordedAt, ScriptedScenes.OriginStart),
                Recorded(ScriptedScenes.Target, LaterRecordedAt, ScriptedScenes.TargetStart),
                Recorded(ScriptedScenes.Filler, LaterRecordedAt, ScriptedScenes.TargetStart),
                .. variants,
            ]));
    }

    public static TheoryData<int, uint, int> KAndTargets()
    {
        TheoryData<int, uint, int> data = [];

        foreach (int k in Enumerable.Range(1, 9))
        {
            data.Add(k, 0, OriginU);
            data.Add(k, 0x20, 0x44);
            data.Add(k, 0x34, 0x58);
        }

        return data;
    }

    private static ValidatedRecording Recorded(Scene scene, int load, HeapSnapshot start) =>
        RecordingLibraryTests.Validated(new ScriptedGame(start, scene.Name).Run(scene, load + 1).Recording);

    private static Scene WithPrefix(uint size) => new(
        $"T{size:X3}",
        [.. ScriptedScenes.Target.Steps.Take(2), new Alloc(size, 16, ScriptedScenes.PlaySite), .. ScriptedScenes.Target.Steps.Skip(2)]);

    private static LoadKey KeyOf(uint prefixSize) =>
        prefixSize is 0 ? TargetKey : new LoadKey(WithPrefix(prefixSize).Name, Costumes.None);

    private static long Delta(long cursor, int u) => (64 - ((cursor + u) % 64)) % 64;

    private static long SphereFromTargetAnchor(int originLoad, int k, int targetU)
    {
        long originCursor = OriginCursorAtLoadTwo + (Leak * (originLoad - OriginRecordedAt));
        long targetCursor = originCursor + (Leak * k);

        return SphereFromOriginAnchor + (OriginU - targetU) - (Leak * k) + Delta(originCursor, OriginU) - Delta(targetCursor, targetU);
    }

    private static LoadKey[] ChainOf(int k, LoadKey target) => [OriginKey, .. Enumerable.Repeat(FillerKey, k - 1), target];

    private static long SphereInTargetLayer(Landing landing)
    {
        LandingWord word = Assert.NotNull(landing.WordAt(ZeroWord));

        Assert.Equal(RegionKind.Block, word.Region.Kind);
        Assert.Equal(0x60000u, word.Region.Block?.Request.Size);
        return (long)word.Region.Offset - ZeroWord;
    }

    private Landing LandingOf(int originLoad, params LoadKey[] loads) =>
        Assert.IsType<Landing>(simulator.Simulate(new ChainPlan(new LoadNumber(originLoad), loads)).Loads[^1].Landing);

    private long[] FourPhases(int k, LoadKey target) =>
        [.. Enumerable.Range(OriginRecordedAt, 4).Select(load => SphereInTargetLayer(LandingOf(load, ChainOf(k, target))))];

    [Theory]
    [InlineData(2, 0x53F7CL)]
    [InlineData(3, 0x53F3CL)]
    [InlineData(4, 0x53F7CL)]
    [InlineData(5, 0x53F7CL)]
    [InlineData(6, 0x53F7CL)]
    [InlineData(7, 0x53F3CL)]
    [InlineData(8, 0x53F7CL)]
    [InlineData(9, 0x53F7CL)]
    public void Landing_EightConsecutiveLoads_MatchesTheWorkedTable(int originLoad, long expected)
    {
        Landing landing = LandingOf(originLoad, OriginKey, TargetKey);

        Assert.Equal(expected, SphereInTargetLayer(landing) + LayerFromTargetAnchor);
    }

    [Theory]
    [MemberData(nameof(KAndTargets))]
    public void Landing_AnyLoadKAndTarget_MatchesTheChainArithmetic(int k, uint prefixSize, int targetU)
    {
        foreach (int originLoad in Enumerable.Range(OriginRecordedAt, 8))
        {
            Landing landing = LandingOf(originLoad, ChainOf(k, KeyOf(prefixSize)));

            Assert.Equal(SphereFromTargetAnchor(originLoad, k, targetU), SphereInTargetLayer(landing) + LayerFromTargetAnchor);
        }
    }

    [Theory]
    [MemberData(nameof(KAndTargets))]
    public void Landing_OverFourPhases_TakesAtMostTwoValuesSixtyFourApart(int k, uint prefixSize, int targetU)
    {
        long[] expected =
        [
            .. Enumerable.Range(OriginRecordedAt, 4)
                .Select(load => SphereFromTargetAnchor(load, k, targetU) - LayerFromTargetAnchor)
                .Distinct()
                .Order(),
        ];

        long[] values = [.. FourPhases(k, KeyOf(prefixSize)).Distinct().Order()];

        Assert.Equal(expected, values);
        Assert.InRange(values.Length, 1, 2);
        Assert.Equal(values.Length is 2 ? 64 : 0, values[^1] - values[0]);
    }

    [Theory]
    [InlineData(1, 0x20u)]
    [InlineData(4, 0x34u)]
    public void Landing_DifferenceInUThatNeverWraps_IsTheSameInEveryPhase(int k, uint prefixSize) =>
        Assert.Single(FourPhases(k, KeyOf(prefixSize)).Distinct());

    [Fact]
    public void Landing_SameUAndKOfOne_SplitsThreePhasesToOne()
    {
        long[] phases = FourPhases(1, TargetKey);

        Assert.Equal([1, 3], phases.GroupBy(static value => value).Select(static group => group.Count()).Order());
    }

    [Theory]
    [InlineData(4)]
    [InlineData(8)]
    public void Landing_SameUAndKAMultipleOfFour_IsTheSameInEveryPhase(int k) =>
        Assert.Single(FourPhases(k, TargetKey).Distinct());

    [Fact]
    public void Landing_EachExtraLoad_MovesEarlierBy704Or768AndAverages720()
    {
        long[] landings = [.. Enumerable.Range(1, 9).Select(k => SphereInTargetLayer(LandingOf(OriginRecordedAt, ChainOf(k, TargetKey))))];

        long[] moves = [.. landings.Zip(landings.Skip(1), static (earlier, later) => earlier - later)];

        Assert.All(moves, static move => Assert.Contains(move, new long[] { 704, 768 }));
        Assert.All(Enumerable.Range(0, moves.Length - 3), first => Assert.Equal(2880, moves.Skip(first).Take(4).Sum()));
    }

    [Fact]
    public void Landing_LoadsBetween_MatterOnlyThroughHowManyThereAre()
    {
        Landing fillers = LandingOf(OriginRecordedAt, OriginKey, FillerKey, FillerKey, FillerKey, TargetKey);
        Landing targets = LandingOf(OriginRecordedAt, OriginKey, TargetKey, TargetKey, TargetKey, TargetKey);
        Landing mixed = LandingOf(OriginRecordedAt, OriginKey, TargetKey, FillerKey, TargetKey, TargetKey);

        Assert.Equal(fillers.Sphere, targets.Sphere);
        Assert.Equal(fillers.Heap, targets.Heap);
        Assert.Equal(fillers.PlayerEntity, mixed.PlayerEntity);
        Assert.Equal(fillers.Words, targets.Words);
        Assert.Equal(fillers.Words, mixed.Words);
    }

    [Fact]
    public void Simulate_FromNotationThroughRecordingText_GivesTheWorkedLandingWithItsBytes()
    {
        ScriptedGame game = new ScriptedGame(ScriptedScenes.OriginStart, "end-to-end")
            .Run(ScriptedScenes.Origin, OriginRecordedAt + 1)
            .Run(ScriptedScenes.Target, LaterRecordedAt + 1, capture: TargetCapture);
        FakeCaptures captures = new(game.CaptureTops);
        Recording read = RecordingReader.Read(new StringReader(game.ManifestText), new StringReader(game.EventText));
        RecordingValidation validation = new ReplayValidator(Platform, captures).Validate(read);
        Assert.True(validation.IsAccepted);
        ChainSimulator wholePath = new(Platform, new RecordingLibrary([validation.Recording]), captures);

        ChainResult result = wholePath.Simulate(ChainPlan.From(Chain.Parse("[load] > burn x1 > ORIG > TARG"), static level => level));

        SimulatedLoad target = result.Loads[^1];
        LandingWord word = Assert.NotNull(target.Landing?.WordAt(0x58));
        const uint recordedAddress = 0x738700 + 0x2A94;
        uint expected = Enumerable.Range(0, 4).Aggregate(0u, static (value, index) => value | ((uint)FakeCapture.ByteAt(recordedAddress + (uint)index) << (8 * index)));

        Assert.Equal(Phase.Fourth, target.Load.Phase);
        Assert.Equal(new SphereAssignment(0, 0x73B43C), target.Landing?.Sphere);
        Assert.Equal(0x6E7200u, target.Landing?.PlayerEntity);
        Assert.Equal(0x738A00u, word.Region.Block?.Address);
        Assert.Equal(0x2A94u, word.Region.Offset);
        Assert.Equal(new OriginalBytes(expected, ByteSource.Capture, recordedAddress), word.Original);
    }

    private static class SecondPlatform
    {
        private const uint EntitySize = 0x2B0;
        private const uint InstanceSize = 0xA4;
        private const uint EntitySite = 0x1100;
        private const uint PoolSite = 0x2200;
        private const uint SphereSite = 0x3300;
        private const uint LayerSite = 0x4400;
        private const uint OtherModelSite = 0x6600;

        private const uint LargePool = 208_752;
        private const uint MediumPool = 50_036;
        private const uint SmallPool = 73_884;

        public static PlatformProfile Profile { get; } = Platform with
        {
            PlayerEntitySize = EntitySize,
            Pools = Platform.Pools with { InstanceSize = InstanceSize },
            Sites = new AllocationSites(EntitySite, PoolSite, SphereSite, LayerSite, 0x5500),
            Platform = "second",
            Footprint = new FootprintProfile([new FootprintWord(0x20, 4, 0), new FootprintWord(0x44, 4, 0x3F800000)]),
        };

        public static ScriptedRules Rules { get; } = new("second", PoolSite, InstanceSize, [(SmallPool, 0x144, 1), (MediumPool, 0x4A, 8), (LargePool, 0x31, 0x40)]);

        public static HeapSnapshot Start { get; } = new([new HeapState(0x5C0030, 0, 0), new HeapState(0x700000, 100, 0x13FFD0)], null);

        public static Scene Origin { get; } = new(
            "ORIG",
            [
                new Alloc(EntitySize, 0, EntitySite),
                new Push(),
                new Alloc(0x10000, 0x40, LayerSite),
                new Push(),
                new Alloc(LargePool, 16, PoolSite),
                new Alloc(MediumPool, 16, PoolSite),
                new Alloc(SmallPool, 16, PoolSite),
                new Pool(0, 0, OtherModelSite),
                new Pool(0, 0, SphereSite),
                new CutoffHere(),
                new ExitScene(),
                new PopTo(1),
            ]);

        public static Scene Target { get; } = new(
            "TARG",
            [
                new Alloc(EntitySize, 0, EntitySite),
                new Push(),
                new Alloc(0x800, 0x40, LayerSite),
                new Push(),
                new Alloc(LargePool, 16, PoolSite),
                new Alloc(MediumPool, 16, PoolSite),
                new Alloc(SmallPool, 16, PoolSite),
                new Alloc(0x60000, 0x40, LayerSite),
                new CutoffHere(),
                new ExitScene(),
                new PopTo(1),
            ]);

        public static ChainSimulator Simulator()
        {
            Recording origin = new ScriptedGame(Start, "origin", Rules).Run(Origin, OriginRecordedAt + 1).Recording;
            Recording target = new ScriptedGame(Start, "target", Rules).Run(Target, LaterRecordedAt + 1).Recording;
            ReplayValidator validator = new(Profile);

            return new ChainSimulator(Profile, new RecordingLibrary([validator.Validate(origin).Recording!, validator.Validate(target).Recording!]));
        }
    }

    [Fact]
    public void SecondPlatform_RecordingsPassValidationOnTheirOwnProfile()
    {
        Recording origin = new ScriptedGame(SecondPlatform.Start, "origin", SecondPlatform.Rules).Run(SecondPlatform.Origin, OriginRecordedAt + 1).Recording;

        Assert.True(new ReplayValidator(SecondPlatform.Profile).Validate(origin).IsAccepted);
    }

    [Fact]
    public void SecondPlatform_RecordingsAreRefusedOnAnotherProfile()
    {
        Recording origin = new ScriptedGame(SecondPlatform.Start, "origin", SecondPlatform.Rules).Run(SecondPlatform.Origin, OriginRecordedAt + 1).Recording;

        Assert.Equal(ReplayCheck.Platform, new ReplayValidator(Platform).Validate(origin).Rejection?.Check);
    }

    [Fact]
    public void SecondPlatform_EveryLeakCosts704()
    {
        ChainSimulator simulator = SecondPlatform.Simulator();

        uint[] spheres = [.. Enumerable.Range(OriginRecordedAt, 5).Select(load => Sphere(simulator, load))];

        Assert.All(spheres.Zip(spheres.Skip(1)), static pair => Assert.Equal(704u, pair.Second - pair.First));
    }

    [Fact]
    public void SecondPlatform_SphereUsesTheProfilesInstanceSize()
    {
        const uint instanceOne = 0x5100 + 0xC + 0xA4;
        Recording origin = new ScriptedGame(SecondPlatform.Start, "origin", SecondPlatform.Rules).Run(SecondPlatform.Origin, OriginRecordedAt + 1).Recording;
        uint pool = ((AllocRequest)origin.Segments[0].Loads[0].Heap.Requests[6]).Address;

        uint sphere = Sphere(SecondPlatform.Simulator(), OriginRecordedAt);

        Assert.Equal(pool + instanceOne, sphere);
    }

    [Fact]
    public void SecondPlatform_LandingIsTheSameOnEveryPhase()
    {
        ChainSimulator simulator = SecondPlatform.Simulator();
        LoadKey[] chain = [OriginKey, TargetKey];

        uint[] offsets =
        [
            .. Enumerable.Range(OriginRecordedAt, 4)
                .Select(load => simulator.Simulate(new ChainPlan(new LoadNumber(load), chain)).Loads[1].Landing!.WordAt(0x20)!.Value.Region.Offset),
        ];

        Assert.Single(offsets.Distinct());
    }

    [Fact]
    public void SecondPlatform_LandingHoldsTheProfilesFootprint()
    {
        ChainResult result = SecondPlatform.Simulator().Simulate(new ChainPlan(new LoadNumber(OriginRecordedAt), [OriginKey, TargetKey]));

        Assert.Equal(SecondPlatform.Profile.Footprint.Words, result.Loads[1].Landing?.Words.Select(static word => word.Word));
    }

    private static uint Sphere(ChainSimulator simulator, int load) =>
        Assert.NotNull(simulator.Simulate(new ChainPlan(new LoadNumber(load), [OriginKey])).Loads[0].Sphere).Address;
}
