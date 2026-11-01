using BowlBuster.Memory;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Replay;

namespace BowlBuster.Tests.Replay;

public class HeapReplayerTests
{
    private const uint PoolSite = 0x182B2A;
    private const uint LayerSite = 0x192860;
    private const uint OtherModelSite = 0x23050;
    private const uint SphereSite = 0xAF43D;

    private const uint OnePoolSize = 72_588;

    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;

    private static readonly HeapSnapshot OriginStart =
        new([new HeapState(0x5C0030, 0, 0), new HeapState(0x6E6C48, 500, 0x126C18)], new HeapBlock(0x6E6990, 0x2B8));

    private static readonly HeapSnapshot OriginEnd =
        new([new HeapState(0x5C0030, 0, 0), new HeapState(0x6E6F18, 501, 0x126EE8)], new HeapBlock(0x749D50, 0x20));

    private static readonly HeapRequest[] Origin =
    [
        new AllocRequest(0x2B8, 0, 0x6E6C60, 0x72670),
        new PushRequest(),
        new AllocRequest(0x10000, 0x40, 0x6E6F40, LayerSite, new LayerId("PLAY", 0)),
        new PushRequest(),
        new PushRequest(),
        new AllocRequest(208_556, 16, 0x6F6F50, PoolSite),
        new AllocRequest(49_740, 16, 0x729E10, PoolSite),
        new AllocRequest(OnePoolSize, 16, 0x736070, PoolSite),
        new AllocRequest(0x2000, 0x40, 0x747C40, LayerSite, new LayerId("ORIG", 0)),
        new GrowRequest(0x100),
        new PoolAllocRequest(0x73B17C, OtherModelSite, 0, 0),
        new PoolAllocRequest(0x73B21C, OtherModelSite, 0, 0),
        new PoolFreeRequest(0x73B17C),
        new PoolAllocRequest(0x73B17C, SphereSite, 0, 0),
        new AllocRequest(0x20, 0, 0x749D50, 0x590B0),
        new PopRequest(1),
    ];

    private static readonly uint?[] OriginResults =
    [
        0x6E6C60, null, 0x6E6F40, null, null, 0x6F6F50, 0x729E10, 0x736070,
        0x747C40, 0x749C40, 0x73B17C, 0x73B21C, null, 0x73B17C, 0x749D50, null,
    ];

    private readonly HeapReplayer replayer;

    public HeapReplayerTests() => replayer = new HeapReplayer(Platform, OriginStart.ToHeap(Platform.Heap0));

    private static uint?[] ApplyAll(HeapReplayer on, IEnumerable<HeapRequest> requests) => [.. requests.Select(on.Apply)];

    [Fact]
    public void Apply_RecordedLoad_ReturnsEveryRecordedResult() =>
        Assert.Equal(OriginResults, ApplyAll(replayer, Origin));

    [Fact]
    public void Apply_RecordedLoad_EndsInTheNextLoadsStartState()
    {
        ApplyAll(replayer, Origin);

        Assert.Null(HeapSnapshot.Of(replayer.Heap).FirstDifference(OriginEnd));
    }

    [Fact]
    public void Apply_UpToTheCutoff_LeavesTheCursorAtTheCapturesTop()
    {
        const int cutoff = 14;

        ApplyAll(replayer, Origin.Take(cutoff));

        Assert.Equal(0x749D40u, replayer.Heap.Current.Cursor);
    }

    [Fact]
    public void Apply_HeapOneLeakLater_FreesThroughTheRecordedAddressAndReusesTheInstance()
    {
        GameHeap heap = OriginStart.ToHeap(Platform.Heap0);
        heap.Allocate(Platform.PlayerEntitySize, 0);
        HeapReplayer shifted = new(Platform, heap);

        uint?[] results = ApplyAll(shifted, Origin);

        Assert.Equal(0x73B43Cu, results[10]);
        Assert.Equal(0x73B4DCu, results[11]);
        Assert.Equal(0x73B43Cu, results[13]);
    }

    [Fact]
    public void Apply_PoolSizedBlockFromAnotherCaller_AddsNoPool()
    {
        replayer.Apply(new AllocRequest(OnePoolSize, 16, 0x736070, LayerSite));

        uint? instance = replayer.Apply(new PoolAllocRequest(0x73B17C, OtherModelSite, 0, 0));

        Assert.Equal(0u, instance);
    }

    [Fact]
    public void Apply_PoolSiteBlockOfAnotherSize_AddsNoPool()
    {
        replayer.Apply(new AllocRequest(OnePoolSize + 4, 16, 0x736070, PoolSite));

        uint? instance = replayer.Apply(new PoolAllocRequest(0x73B17C, OtherModelSite, 0, 0));

        Assert.Equal(0u, instance);
    }

    [Fact]
    public void Apply_PoolBlockThatDoesNotFit_AddsNoPool()
    {
        PlatformProfile tight = Platform with { Heap0 = Platform.Heap0 with { Size = OnePoolSize } };
        HeapReplayer full = new(tight, new HeapSnapshot([new HeapState(0x700000, 0, 0)], null).ToHeap(tight.Heap0));

        uint? block = full.Apply(new AllocRequest(OnePoolSize, 16, 0x736070, PoolSite));
        uint? instance = full.Apply(new PoolAllocRequest(0x73B17C, OtherModelSite, 0, 0));

        Assert.Equal(0u, block);
        Assert.Equal(0u, instance);
    }

    [Fact]
    public void Apply_ModelWithANodeAndTheExtraFlag_NeedsMoreThanTheOneMatrixPool()
    {
        ApplyAll(replayer, Origin.Take(8));

        uint? instance = replayer.Apply(new PoolAllocRequest(0x73321C, OtherModelSite, 1, 0x40));

        Assert.Equal(0x73321Cu, instance);
    }

    [Fact]
    public void Apply_NoPoolsYet_PoolAllocationReturnsZero() =>
        Assert.Equal(0u, replayer.Apply(new PoolAllocRequest(0x73B17C, SphereSite, 0, 0)));

    [Fact]
    public void Apply_FreeBeforeAnyPool_IsIgnored() =>
        Assert.Null(replayer.Apply(new PoolFreeRequest(0x73B17C)));

    [Fact]
    public void Apply_SizeZeroAllocation_ReturnsTheGamesSentinel() =>
        Assert.Equal(GameHeap.ZeroSizeAddress, replayer.Apply(new AllocRequest(0, 0, GameHeap.ZeroSizeAddress, 0x590B0)));

    [Fact]
    public void Apply_NewReplayerOnTheSameHeap_HasNoPoolsFromTheLastLoad()
    {
        ApplyAll(replayer, Origin);
        HeapReplayer nextLoad = new(Platform, replayer.Heap);

        uint? instance = nextLoad.Apply(new PoolAllocRequest(0x73B17C, OtherModelSite, 0, 0));

        Assert.Equal(0u, instance);
    }

    private sealed record UnknownRequest : HeapRequest;

    [Fact]
    public void Apply_UnknownRequest_Throws() =>
        Assert.Throws<ArgumentException>(() => replayer.Apply(new UnknownRequest()));

    [Fact]
    public void Apply_PopAboveTheCurrentDepth_Throws() =>
        Assert.Throws<ArgumentOutOfRangeException>(() => replayer.Apply(new PopRequest(9)));

    [Fact]
    public void Apply_GrowWithNoLastBlock_Throws()
    {
        HeapReplayer empty = new(Platform, new HeapSnapshot([new HeapState(0x700000, 0, 0)], null).ToHeap(Platform.Heap0));

        Assert.Throws<InvalidOperationException>(() => empty.Apply(new GrowRequest(4)));
    }
}
