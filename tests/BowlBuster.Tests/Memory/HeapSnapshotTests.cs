using BowlBuster.Memory;
using BowlBuster.Platforms;

namespace BowlBuster.Tests.Memory;

public class HeapSnapshotTests
{
    private static readonly HeapProfile Profile = PlatformProfile.XboxNtscU.Heap0;

    private readonly HeapSnapshot snapshot;

    public HeapSnapshotTests() =>
        snapshot = new HeapSnapshot([new HeapState(0x5C0030, 0, 0), new HeapState(0x6E6C48, 500, 0x126C18)], new HeapBlock(0x6E6990, 0x2B8));

    private HeapSnapshot WithState(int depth, Func<HeapState, HeapState> change) =>
        snapshot with { States = [.. snapshot.States.Select((state, index) => index == depth ? change(state) : state)] };

    [Fact]
    public void Depth_TwoStates_IsTheLastIndex() => Assert.Equal(1, snapshot.Depth);

    [Fact]
    public void ToHeapThenOf_ALastBlock_RoundTrips()
    {
        HeapSnapshot roundTripped = HeapSnapshot.Of(snapshot.ToHeap(Profile));

        Assert.Null(roundTripped.FirstDifference(snapshot));
    }

    [Fact]
    public void ToHeapThenOf_NoLastBlock_RoundTrips()
    {
        HeapSnapshot empty = snapshot with { LastBlock = null };

        HeapSnapshot roundTripped = HeapSnapshot.Of(empty.ToHeap(Profile));

        Assert.Null(roundTripped.LastBlock);
        Assert.Null(roundTripped.FirstDifference(empty));
    }

    [Fact]
    public void Of_HeapChangedLater_KeepsTheStateItTook()
    {
        GameHeap heap = snapshot.ToHeap(Profile);
        HeapSnapshot taken = HeapSnapshot.Of(heap);

        heap.Allocate(0x20, 0);
        heap.Push();

        Assert.Null(taken.FirstDifference(snapshot));
    }

    [Fact]
    public void FirstDifference_EqualStates_IsNull()
    {
        HeapSnapshot equal = snapshot with { States = [.. snapshot.States] };

        Assert.Null(snapshot.FirstDifference(equal));
    }

    [Fact]
    public void FirstDifference_OtherDepth_NamesTheDepthBeforeAnythingElse()
    {
        HeapSnapshot deeper = new([new HeapState(1, 1, 1), new HeapState(2, 2, 2), new HeapState(3, 3, 3)], null);

        HeapDifference? difference = snapshot.FirstDifference(deeper);

        Assert.Equal(new HeapDifference("depth", 1, 2), difference);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    public void FirstDifference_OtherCursor_NamesTheDepthsCursor(int depth)
    {
        uint cursor = snapshot.States[depth].Cursor;
        HeapSnapshot other = WithState(depth, static state => state with { Cursor = state.Cursor + 4 });

        HeapDifference? difference = snapshot.FirstDifference(other);

        Assert.Equal(new HeapDifference($"states[{depth}].cursor", cursor, cursor + 4), difference);
    }

    [Fact]
    public void FirstDifference_OtherBlockCount_NamesTheDepthsBlocks()
    {
        HeapSnapshot other = WithState(1, static state => state with { BlockCount = 501 });

        HeapDifference? difference = snapshot.FirstDifference(other);

        Assert.Equal(new HeapDifference("states[1].blocks", 500, 501), difference);
    }

    [Fact]
    public void FirstDifference_OtherUsed_NamesTheDepthsUsed()
    {
        HeapSnapshot other = WithState(1, static state => state with { Used = 0x126EE8 });

        HeapDifference? difference = snapshot.FirstDifference(other);

        Assert.Equal(new HeapDifference("states[1].used", 0x126C18, 0x126EE8), difference);
    }

    [Fact]
    public void FirstDifference_TwoDepthsDiffer_NamesTheShallowerFirst()
    {
        HeapSnapshot other = new([new HeapState(0x5C0040, 0, 0), new HeapState(0x6E6C4C, 500, 0x126C18)], snapshot.LastBlock);

        HeapDifference? difference = snapshot.FirstDifference(other);

        Assert.Equal("states[0].cursor", difference?.Field);
    }

    [Fact]
    public void FirstDifference_OtherLastBlockAddress_NamesTheAddress()
    {
        HeapSnapshot other = snapshot with { LastBlock = new HeapBlock(0x6E6C60, 0x2B8) };

        HeapDifference? difference = snapshot.FirstDifference(other);

        Assert.Equal(new HeapDifference("last_block.address", 0x6E6990, 0x6E6C60), difference);
    }

    [Fact]
    public void FirstDifference_OtherLastBlockSize_NamesTheSize()
    {
        HeapSnapshot other = snapshot with { LastBlock = new HeapBlock(0x6E6990, 0x2BC) };

        HeapDifference? difference = snapshot.FirstDifference(other);

        Assert.Equal(new HeapDifference("last_block.size", 0x2B8, 0x2BC), difference);
    }

    [Fact]
    public void FirstDifference_LastBlockOnThisSideOnly_NamesTheLastBlock()
    {
        HeapSnapshot other = snapshot with { LastBlock = null };

        HeapDifference? difference = snapshot.FirstDifference(other);

        Assert.Equal(new HeapDifference("last_block", 0x6E6990, null), difference);
    }

    [Fact]
    public void FirstDifference_LastBlockOnTheOtherSideOnly_NamesTheLastBlock()
    {
        HeapSnapshot without = snapshot with { LastBlock = null };

        HeapDifference? difference = without.FirstDifference(snapshot);

        Assert.Equal(new HeapDifference("last_block", null, 0x6E6990), difference);
    }

    [Fact]
    public void ToHeap_NoStates_Throws()
    {
        HeapSnapshot empty = new([], null);

        Assert.Throws<ArgumentException>(() => empty.ToHeap(Profile));
    }
}
