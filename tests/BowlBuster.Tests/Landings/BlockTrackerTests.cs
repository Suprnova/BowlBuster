using BowlBuster.Landings;
using BowlBuster.Memory;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Replay;
using System.Diagnostics;

namespace BowlBuster.Tests.Landings;

public class BlockTrackerTests
{
    private const uint PlaySite = 0x590B0;
    private const uint StartCursor = 0x6E6C48;
    private const uint EntitySize = 0x2B8;

    private const int NoOrigin = -1;

    private const int OpA = 0;
    private const int OpB = 1;
    private const int OpC = 2;

    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;

    private readonly GameHeap heap;
    private readonly HeapReplayer replayer;
    private readonly BlockTracker tracker;

    private int nextOp;

    public BlockTrackerTests()
    {
        heap = new GameHeap(Platform.Heap0, [new HeapState(StartCursor, 0, 0)]);
        replayer = new HeapReplayer(Platform, heap);
        tracker = new BlockTracker(Platform.Heap0);
        BeginLoad();
    }

    private static AllocRequest Alloc(uint size, uint alignment) => new(size, alignment, 0, PlaySite);

    private void BeginLoad()
    {
        tracker.BeginLoad();
        nextOp = 0;
    }

    private void Run(params HeapRequest[] requests)
    {
        foreach (HeapRequest request in requests)
        {
            tracker.Apply(replayer, nextOp++, request);
        }
    }

    private void RunLeakAndPush(uint blockSize)
    {
        Run(Alloc(EntitySize, 0), new PushRequest(), Alloc(blockSize, 0x40));
    }

    [Fact]
    public void Apply_ThreeBlocks_RecordsWhereEachHeaderAndBlockFall()
    {
        Run(Alloc(EntitySize, 0), Alloc(0x101, 0x40), Alloc(0x10, 16));

        Assert.Equal((0x6E6C48u, 0x6E6C60u, 0x6E6F18u), Extent(OpA));
        Assert.Equal((0x6E6F18u, 0x6E6F40u, 0x6E7041u), Extent(OpB));
        Assert.Equal((0x6E7044u, 0x6E7050u, 0x6E7060u), Extent(OpC));
    }

    private (uint Header, uint Address, uint End) Extent(int op)
    {
        PlacedBlock block = Assert.NotNull(tracker.Find(op));
        return (block.Header, block.Address, block.End);
    }

    [Theory]
    [InlineData(0x6E6C70u, RegionKind.Block, OpA, 0x10u)]
    [InlineData(0x6E6F20u, RegionKind.Header, OpB, 8u)]
    [InlineData(0x6E6F24u, RegionKind.Padding, OpB, 0x1Cu)]
    [InlineData(0x6E7040u, RegionKind.Block, OpB, 0x100u)]
    [InlineData(0x6E7041u, RegionKind.Padding, OpC, 0xFu)]
    [InlineData(0x6E7044u, RegionKind.Header, OpC, 0u)]
    [InlineData(0x6E7068u, RegionKind.Block, OpC, 0x18u)]
    public void Locate_AnAddressInTheHeap_NamesTheRegionTheBlockAndTheOffset(uint address, RegionKind kind, int op, uint offset)
    {
        Run(Alloc(EntitySize, 0), Alloc(0x101, 0x40), Alloc(0x10, 16), new GrowRequest(0x10));

        LandingRegion region = tracker.Locate(address, NoOrigin);

        Assert.Equal(kind, region.Kind);
        Assert.Equal(op, region.Block?.Op);
        Assert.Equal(offset, region.Offset);
    }

    [Theory]
    [InlineData(0x6E7070u)]
    [InlineData(0x700000u)]
    public void Locate_PastEverythingAllocated_IsAboveTheHeapWithNoBlock(uint address)
    {
        Run(Alloc(EntitySize, 0), Alloc(0x101, 0x40), Alloc(0x10, 16), new GrowRequest(0x10));

        Assert.Equal(new LandingRegion(RegionKind.AboveHeap, null, 0), tracker.Locate(address, NoOrigin));
    }

    [Fact]
    public void Locate_BelowEveryBlock_IsUnreachable()
    {
        Run(Alloc(EntitySize, 0));

        Assert.Throws<UnreachableException>(() => tracker.Locate(0x6E6C5C, NoOrigin));
    }

    [Fact]
    public void Locate_GrownBytesBeforeTheGrow_AreNotYetTheBlocks()
    {
        Run(Alloc(0x10, 16));
        PlacedBlock block = Assert.NotNull(tracker.Find(0));

        RegionKind before = tracker.Locate(block.End, NoOrigin).Kind;
        Run(new GrowRequest(0x10));
        RegionKind after = tracker.Locate(block.End, NoOrigin).Kind;

        Assert.Equal(RegionKind.AboveHeap, before);
        Assert.Equal(RegionKind.Block, after);
    }

    [Fact]
    public void Apply_GrowRoundsUp_LikeTheHeap()
    {
        Run(Alloc(0x10, 16), new GrowRequest(5));

        Assert.Equal(0x18u, tracker.Find(0)?.Size);
    }

    [Fact]
    public void Apply_GrowingAPoppedBlock_ChangesNoLiveBlock()
    {
        Run(Alloc(EntitySize, 0), new PushRequest(), Alloc(0x10, 16), new PopRequest(0), new GrowRequest(0x10));

        Assert.Equal(EntitySize, tracker.Find(0)?.Size);
    }

    [Fact]
    public void Apply_SizeZeroAllocation_PlacesNoBlock()
    {
        Run(Alloc(0, 0));

        Assert.Null(tracker.Find(0));
    }

    [Fact]
    public void Apply_FailedAllocation_PlacesNoBlock()
    {
        Run(Alloc(Platform.Heap0.Size + 1, 0));

        Assert.Null(tracker.Find(0));
    }

    [Fact]
    public void Apply_ReturnsWhatTheReplayerReturned()
    {
        uint? address = tracker.Apply(replayer, 0, Alloc(EntitySize, 0));

        Assert.Equal(0x6E6C60u, address);
    }

    [Fact]
    public void Find_PushesAndPops_PlaceNoBlock()
    {
        Run(new PushRequest(), new PopRequest(0));

        Assert.Null(tracker.Find(0));
        Assert.Null(tracker.Find(1));
    }

    [Fact]
    public void Find_PoppedBlock_IsStillFound()
    {
        Run(new PushRequest(), Alloc(0x20, 16), new PopRequest(0));

        Assert.Equal(0x20u, tracker.Find(1)?.Size);
    }

    [Fact]
    public void Find_OpOfAnEarlierLoad_IsNotThisLoads()
    {
        Run(Alloc(EntitySize, 0));
        BeginLoad();

        Assert.Null(tracker.Find(0));
    }

    [Fact]
    public void HeapTop_AfterABlockAndAGrow_IsTheirEnd()
    {
        Run(Alloc(0x10, 16), new GrowRequest(0x10));

        Assert.Equal(0x6E6C60u + 0x20u, tracker.HeapTop);
    }

    [Fact]
    public void HeapTop_NextLoad_StartsAtTheLiveBlocks()
    {
        RunLeakAndPush(0x1000);
        Run(new PopRequest(0));

        BeginLoad();

        Assert.Equal(0x6E6F18u, tracker.HeapTop);
    }

    [Fact]
    public void Locate_MemoryPoppedInThisLoad_IsFreedAndNamesTheBlockThatHeldIt()
    {
        Run(Alloc(EntitySize, 0), new PushRequest(), Alloc(0x100, 0x40), new PopRequest(0), Alloc(0x10, 16));

        LandingRegion region = tracker.Locate(0x6E6F80, NoOrigin);

        Assert.Equal(RegionKind.Freed, region.Kind);
        Assert.Equal(2, region.Block?.Op);
        Assert.Equal(0x40u, region.Offset);
    }

    [Fact]
    public void Locate_GapBetweenTwoPoppedBlocks_IsFreedWithNoBlock()
    {
        Run(Alloc(EntitySize, 0), new PushRequest(), Alloc(0x10, 16), Alloc(0x100, 0x40), new PopRequest(0), Alloc(0x4, 16));
        PlacedBlock first = Assert.NotNull(tracker.Find(2));

        LandingRegion region = tracker.Locate(first.End + 4, NoOrigin);

        Assert.Equal(new LandingRegion(RegionKind.Freed, null, 0), region);
    }

    [Fact]
    public void Locate_PastThePoppedBlock_IsAboveTheHeap()
    {
        Run(Alloc(EntitySize, 0), new PushRequest(), Alloc(0x100, 0x40), new PopRequest(0), Alloc(0x10, 16));

        Assert.Equal(RegionKind.AboveHeap, tracker.Locate(0x6E7040, NoOrigin).Kind);
    }

    [Fact]
    public void Locate_LeakOfAnEarlierLoad_SurvivesThePopWithItsOwnPosition()
    {
        RunLeakAndPush(0x1000);
        Run(new PopRequest(0));
        BeginLoad();
        RunLeakAndPush(0x10);

        LandingRegion region = tracker.Locate(0x6E6C68, NoOrigin);

        Assert.Equal(RegionKind.Block, region.Kind);
        Assert.Equal(0, region.Block?.Position);
        Assert.Equal(0, region.Block?.Op);
        Assert.Equal(8u, region.Offset);
    }

    [Fact]
    public void Locate_BlockAPopEnded_IsNoLongerLive()
    {
        RunLeakAndPush(0x1000);
        Run(new PopRequest(0));
        BeginLoad();

        Assert.Equal(RegionKind.AboveHeap, tracker.Locate(0x6E6F40, NoOrigin).Kind);
    }

    [Fact]
    public void PopTo_LikeARecordedPop_EndsTheBlocksAboveTheCursor()
    {
        RunLeakAndPush(0x1000);

        tracker.PopTo(heap, 0);
        BeginLoad();

        Assert.Equal(0, heap.Depth);
        Assert.Equal(RegionKind.AboveHeap, tracker.Locate(0x6E6F40, NoOrigin).Kind);
    }

    [Fact]
    public void Locate_AboveThisLoadsHeap_NamesTheNewestEarlierLoadThatCoveredIt()
    {
        const int origin = 0;
        RunLeakAndPush(0x10);
        Run(new PopRequest(0));
        BeginLoad();
        RunLeakAndPush(0x1000);
        Run(new PopRequest(0));
        BeginLoad();
        RunLeakAndPush(0x800);
        Run(new PopRequest(0));
        BeginLoad();
        RunLeakAndPush(0x10);
        const uint heldByLoadOneOnly = 0x6E8000;

        LandingRegion region = tracker.Locate(heldByLoadOneOnly, origin);

        Assert.Equal(RegionKind.AboveHeap, region.Kind);
        Assert.Equal(1, region.Block?.Position);
        Assert.Equal(2, region.Block?.Op);
        Assert.Equal(heldByLoadOneOnly - region.Block?.Address, region.Offset);
    }

    [Fact]
    public void Locate_TwoEarlierLoadsCoveredIt_PrefersTheNewer()
    {
        const int origin = 0;
        RunLeakAndPush(0x10);
        Run(new PopRequest(0));
        BeginLoad();
        RunLeakAndPush(0x1000);
        Run(new PopRequest(0));
        BeginLoad();
        RunLeakAndPush(0x1000);
        Run(new PopRequest(0));
        BeginLoad();
        RunLeakAndPush(0x10);

        LandingRegion region = tracker.Locate(0x6E7C00, origin);

        Assert.Equal(2, region.Block?.Position);
    }

    [Fact]
    public void Locate_BlockAnEarlierLoadPlacedAfterItsCutoff_Counts()
    {
        const int origin = 0;
        RunLeakAndPush(0x10);
        Run(new PopRequest(0));
        BeginLoad();
        RunLeakAndPush(0x10);
        Run(Alloc(0x4000, 0x40));
        PlacedBlock late = Assert.NotNull(tracker.Find(3));
        Run(new PopRequest(0));
        BeginLoad();
        RunLeakAndPush(0x10);

        LandingRegion region = tracker.Locate(late.Address + 0x2000, origin);

        Assert.Equal(RegionKind.AboveHeap, region.Kind);
        Assert.Equal(3, region.Block?.Op);
        Assert.Equal(0x2000u, region.Offset);
    }

    [Fact]
    public void Locate_OnlyTheOriginCoveredIt_HasNoBlock()
    {
        const int origin = 0;
        RunLeakAndPush(0x4000);
        Run(new PopRequest(0));
        BeginLoad();
        RunLeakAndPush(0x10);
        Run(new PopRequest(0));
        BeginLoad();
        RunLeakAndPush(0x10);

        Assert.Equal(new LandingRegion(RegionKind.AboveHeap, null, 0), tracker.Locate(0x6E8000, origin));
    }

    [Fact]
    public void Locate_LoadBeforeTheOriginCoveredIt_HasNoBlock()
    {
        const int origin = 1;
        RunLeakAndPush(0x4000);
        Run(new PopRequest(0));
        BeginLoad();
        RunLeakAndPush(0x10);
        Run(new PopRequest(0));
        BeginLoad();
        RunLeakAndPush(0x10);

        Assert.Null(tracker.Locate(0x6E8000, origin).Block);
    }
}
