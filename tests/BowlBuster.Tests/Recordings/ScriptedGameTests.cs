using BowlBuster.Memory;
using BowlBuster.Recordings;

namespace BowlBuster.Tests.Recordings;

public class ScriptedGameTests
{
    private readonly ScriptedGame game;

    public ScriptedGameTests() =>
        game = new ScriptedGame(ScriptedScenes.OriginStart)
            .Run(ScriptedScenes.Origin, 3, capture: "origin-cutoff")
            .Run(ScriptedScenes.Target, 4, capture: "target-cutoff");

    private RecordedLoad Origin => game.Recording.Segments[0].Loads[0];

    private RecordedLoad Target => game.Recording.Segments[0].Loads[1];

    private static uint AllocAddress(RecordedLoad load, int op) => ((AllocRequest)load.Heap.Requests[op]).Address;

    private static uint PoolInstance(RecordedLoad load, int op) => ((PoolAllocRequest)load.Heap.Requests[op]).Instance;

    [Theory]
    [InlineData(0, 0x6E6C60u)]
    [InlineData(2, 0x6E6F40u)]
    [InlineData(5, 0x6F6F50u)]
    [InlineData(6, 0x729E10u)]
    [InlineData(7, 0x736070u)]
    [InlineData(8, 0x747C40u)]
    [InlineData(14, 0x749D50u)]
    public void Run_Origin_PlacesEveryBlockAtItsHandComputedAddress(int op, uint expected) =>
        Assert.Equal(expected, AllocAddress(Origin, op));

    [Theory]
    [InlineData(10, 0x73B17Cu)]
    [InlineData(11, 0x73B21Cu)]
    [InlineData(13, 0x73B17Cu)]
    public void Run_Origin_ReusesTheFreedInstanceForTheSphere(int op, uint expected) =>
        Assert.Equal(expected, PoolInstance(Origin, op));

    [Fact]
    public void Run_Origin_FreesTheFirstInstance() =>
        Assert.Equal(new PoolFreeRequest(0x73B17C), Origin.Heap.Requests[12]);

    [Theory]
    [InlineData(0, 0x6E6F30u)]
    [InlineData(2, 0x6E7200u)]
    [InlineData(8, 0x738700u)]
    [InlineData(10, 0x798750u)]
    public void Run_Target_PlacesEveryBlockAtItsHandComputedAddress(int op, uint expected) =>
        Assert.Equal(expected, AllocAddress(Target, op));

    [Fact]
    public void Run_Origin_LeavesTheTargetsHandComputedStartState() =>
        Assert.Null(Target.Heap.Start.FirstDifference(ScriptedScenes.TargetStart));

    [Fact]
    public void Run_Cutoffs_FallAfterTheLastRequestBeforeTheDraw()
    {
        Assert.Equal(14, Origin.Heap.Cutoff?.RequestCount);
        Assert.Equal(11, Target.Heap.Cutoff?.RequestCount);
    }

    [Fact]
    public void Run_Captures_HoldTheCursorAtEachCutoff()
    {
        Assert.Equal(0x749D40u, game.CaptureTops["origin-cutoff"]);
        Assert.Equal(0x79876Cu, game.CaptureTops["target-cutoff"]);
    }

    [Fact]
    public void Run_Loads_CountFromTheBootCounter()
    {
        Assert.Equal(2, Origin.Load?.Value);
        Assert.Equal(3, Target.Load?.Value);
    }

    [Fact]
    public void Run_SizeZeroAllocation_ReturnsTheGamesSentinelAndMovesNothing()
    {
        ScriptedGame sized = new ScriptedGame(ScriptedScenes.OriginStart).Run(new Scene("NONE", [new Alloc(0, 0, ScriptedScenes.PlaySite)]), 3);

        Assert.Equal(GameHeap.ZeroSizeAddress, AllocAddress(sized.Recording.Segments[0].Loads[0], 0));
        Assert.Equal(0x6E6C48u, sized.Cursor);
    }
}
