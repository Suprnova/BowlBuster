using BowlBuster.Memory;
using BowlBuster.Placement;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Replay;
using BowlBuster.Tests.Recordings;

namespace BowlBuster.Tests.Placement;

public sealed class PlacerTests
{
    private const int Counter = 3;
    private const int LayerOp = 8;
    private const int EntityOp = 0;
    private const int SphereOp = 13;
    private const uint LeakCost = 720;

    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;
    private static readonly Placer Placer = new(Platform);

    private static ValidatedRecording Validated(ScriptedGame game) => new ReplayValidator(Platform).Validate(game.Recording).Recording!;

    private static ScriptedGame OneOrigin() => new ScriptedGame(ScriptedScenes.OriginStart).Run(ScriptedScenes.Origin, Counter);

    private static RecordedLoad OriginLoad(ScriptedGame game) => game.Recording.Segments[0].Loads[0];

    private static uint RecordedAddress(ScriptedGame game, int op) => OriginLoad(game).Heap.Requests[op] switch
    {
        AllocRequest alloc => alloc.Address,
        PoolAllocRequest instance => instance.Instance,
        _ => throw new ArgumentOutOfRangeException(nameof(op)),
    };

    [Fact]
    public void Place_LiveHeapAtTheRecordedStart_GivesTheRecordedBlockPlusTheDelta()
    {
        ScriptedGame game = OneOrigin();

        PlacementResult result = Placer.Place(Validated(game), Counter, null, ScriptedScenes.OriginStart, LayerOp, 0x10);

        Assert.Equal(RecordedAddress(game, LayerOp) + 0x10, Assert.IsType<Placed>(result).Sphere);
    }

    [Fact]
    public void Place_ModelPoolInstance_IsABlock()
    {
        ScriptedGame game = OneOrigin();

        PlacementResult result = Placer.Place(Validated(game), Counter, null, ScriptedScenes.OriginStart, SphereOp, 0);

        Assert.Equal(RecordedAddress(game, SphereOp), Assert.IsType<Placed>(result).Sphere);
    }

    [Fact]
    public void Place_ShiftedLiveHeap_GivesTheShiftedAddress()
    {
        ScriptedGame game = OneOrigin();

        PlacementResult result = Placer.Place(Validated(game), Counter, null, ScriptedScenes.StartAfterLeaks(1), EntityOp, 0);

        Assert.Equal(RecordedAddress(game, EntityOp) + LeakCost, Assert.IsType<Placed>(result).Sphere);
    }

    [Fact]
    public void Place_NegativeDelta_CountsBackFromTheBlock()
    {
        ScriptedGame game = OneOrigin();

        PlacementResult result = Placer.Place(Validated(game), Counter, null, ScriptedScenes.OriginStart, LayerOp, -0x18);

        Assert.Equal(RecordedAddress(game, LayerOp) - 0x18, Assert.IsType<Placed>(result).Sphere);
    }

    [Fact]
    public void Place_DeltaPastAddressZero_WrapsTo32Bits()
    {
        ScriptedGame game = OneOrigin();

        PlacementResult result = Placer.Place(Validated(game), Counter, null, ScriptedScenes.OriginStart, EntityOp, int.MinValue);

        Assert.Equal(unchecked(RecordedAddress(game, EntityOp) + 0x8000_0000u), Assert.IsType<Placed>(result).Sphere);
    }

    [Fact]
    public void Place_LoadWithACutoff_GivesTheCursorAndDepthThere()
    {
        ScriptedGame game = new ScriptedGame(ScriptedScenes.OriginStart).Run(ScriptedScenes.Origin, Counter, capture: "0-3-cutoff");

        PlacementResult result = Placer.Place(Validated(game), Counter, null, ScriptedScenes.OriginStart, EntityOp, 0);

        Assert.Equal(new HeapTop(game.CaptureTops["0-3-cutoff"], 4), Assert.IsType<Placed>(result).Top);
    }

    [Fact]
    public void Place_LoadWithoutACutoff_GivesNoTop()
    {
        Scene uncut = new("UNCU", [new Alloc(0x40, 0, ScriptedScenes.PlaySite)]);
        ScriptedGame game = new ScriptedGame(ScriptedScenes.OriginStart).Run(uncut, Counter);

        PlacementResult result = Placer.Place(Validated(game), Counter, null, ScriptedScenes.OriginStart, 0, 0);

        Assert.Null(Assert.IsType<Placed>(result).Top);
    }

    [Fact]
    public void Place_OpPastTheRequestList_PlacesNoBlock()
    {
        ScriptedGame game = OneOrigin();

        PlacementResult result = Placer.Place(Validated(game), Counter, null, ScriptedScenes.OriginStart, 99, 0);

        Assert.Contains("no op 99", Assert.IsType<NoBlock>(result).Reason, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(1, "a push")]
    [InlineData(9, "a grow")]
    [InlineData(12, "a free")]
    public void Place_OpThatMakesNoBlock_PlacesNoBlock(int op, string kind)
    {
        ScriptedGame game = OneOrigin();

        PlacementResult result = Placer.Place(Validated(game), Counter, null, ScriptedScenes.OriginStart, op, 0);

        Assert.Contains(kind, Assert.IsType<NoBlock>(result).Reason, StringComparison.Ordinal);
    }

    [Fact]
    public void Place_LoadNoSegmentHolds_IsUnplaceable()
    {
        ScriptedGame game = OneOrigin();

        PlacementResult result = Placer.Place(Validated(game), 7, null, ScriptedScenes.OriginStart, EntityOp, 0);

        Assert.IsType<Unplaceable>(result);
    }

    [Fact]
    public void Place_LoadTwoSegmentsHold_NamesThemUnlessOneIsGiven()
    {
        ScriptedGame game = OneOrigin().BeginSegment(ScriptedScenes.StartAfterLeaks(1)).Run(ScriptedScenes.Origin, Counter);

        PlacementResult unnamed = Placer.Place(Validated(game), Counter, null, ScriptedScenes.OriginStart, EntityOp, 0);
        PlacementResult named = Placer.Place(Validated(game), Counter, 1, ScriptedScenes.OriginStart, EntityOp, 0);

        Assert.Equal([0, 1], Assert.IsType<AmbiguousLoad>(unnamed).Segments);
        Assert.IsType<Placed>(named);
    }
}
