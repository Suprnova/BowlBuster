using BowlBuster.Memory;
using BowlBuster.Platforms;

namespace BowlBuster.Tests.Memory;

public class GameHeapTests
{
    private static readonly HeapProfile Profile = PlatformProfile.XboxNtscU.Heap0;
    private static readonly uint PlayerEntitySize = PlatformProfile.XboxNtscU.PlayerEntitySize;

    private const uint BootCursor = 0x5C0030;
    private const uint LeakCursor = 0x6E6980;

    private static GameHeap CreateHeap(uint cursor, HeapProfile? profile = null) =>
        new(profile ?? Profile, [new HeapState(cursor, 0, 0)]);

    private static uint AlignUp(uint value, uint alignment) => (value + alignment - 1) & ~(alignment - 1);

    [Fact]
    public void Allocate_PlayerEntityAtRecordedCursor_ReturnsRecordedAddressAndCursor()
    {
        GameHeap heap = CreateHeap(LeakCursor);

        uint address = heap.Allocate(PlayerEntitySize, 0);

        Assert.Equal(0x6E6990u, address);
        Assert.Equal(0x6E6C48u, heap.Current.Cursor);
    }

    [Theory]
    [InlineData(0u, 0x2C8u)]
    [InlineData(4u, 0x2C4u)]
    [InlineData(8u, 0x2D0u)]
    [InlineData(12u, 0x2CCu)]
    public void Allocate_FirstLeak_CostsByCursorResidue(uint residue, uint expectedCost)
    {
        GameHeap heap = CreateHeap(LeakCursor + residue);

        heap.Allocate(PlayerEntitySize, 0);

        Assert.Equal(expectedCost, heap.Current.Cursor - (LeakCursor + residue));
    }

    [Fact]
    public void Allocate_LeaksAfterTheFirst_Cost720BytesFromAnEightResidueCursor()
    {
        GameHeap heap = CreateHeap(LeakCursor);
        heap.Allocate(PlayerEntitySize, 0);

        for (int leak = 0; leak < 8; leak++)
        {
            uint before = heap.Current.Cursor;

            heap.Allocate(PlayerEntitySize, 0);

            Assert.Equal(8u, before % 16);
            Assert.Equal(720u, heap.Current.Cursor - before);
        }
    }

    [Theory]
    [InlineData(0u)]
    [InlineData(4u)]
    [InlineData(8u)]
    [InlineData(16u)]
    [InlineData(32u)]
    [InlineData(64u)]
    public void Allocate_AnyAlignment_PlacesBlockAtDefaultOrRequestedAlignmentPastTheAllowance(uint alignment)
    {
        const uint cursor = 0x6E6C48;
        GameHeap heap = CreateHeap(cursor);

        uint address = heap.Allocate(100, alignment);

        Assert.Equal(AlignUp(cursor + 12, Math.Max(alignment, 16)), address);
    }

    [Theory]
    [InlineData(1u)]
    [InlineData(101u)]
    [InlineData(102u)]
    [InlineData(103u)]
    [InlineData(104u)]
    public void Allocate_AnySize_AdvancesCursorToNextMultipleOfFourPastTheBlock(uint size)
    {
        GameHeap heap = CreateHeap(BootCursor);

        uint address = heap.Allocate(size, 16);

        Assert.Equal(AlignUp(address + size, 4), heap.Current.Cursor);
    }

    [Fact]
    public void Allocate_Block_UpdatesCountUsedAndLastBlock()
    {
        GameHeap heap = CreateHeap(BootCursor);

        uint address = heap.Allocate(101, 16);

        Assert.Equal(new HeapState(BootCursor + 120, 1, 120), heap.Current);
        Assert.Equal(new HeapBlock(address, 101), heap.LastBlock);
    }

    [Fact]
    public void Allocate_RecordedBootSequence_ReturnsRecordedAddresses()
    {
        uint[] sizes = [1024, 1024, 2048, 2048, 4096, 4096, 8192, 16384];
        uint[] expected = [0x5C0040, 0x5C0450, 0x5C0860, 0x5C1070, 0x5C1880, 0x5C2890, 0x5C38A0, 0x5C58B0];
        GameHeap heap = CreateHeap(BootCursor);

        uint[] addresses = [.. sizes.Select(size => heap.Allocate(size, 16))];

        Assert.Equal(expected, addresses);
    }

    [Fact]
    public void Allocate_SizeZero_ReturnsSentinelAndKeepsState()
    {
        GameHeap heap = CreateHeap(BootCursor);
        heap.Allocate(64, 16);
        HeapState before = heap.Current;
        HeapBlock? lastBlock = heap.LastBlock;

        uint address = heap.Allocate(0, 64);

        Assert.Equal(GameHeap.ZeroSizeAddress, address);
        Assert.Equal(before, heap.Current);
        Assert.Equal(lastBlock, heap.LastBlock);
    }

    [Theory]
    [InlineData(24u)]
    [InlineData(48u)]
    [InlineData(100u)]
    public void Allocate_AlignmentNotAPowerOfTwo_Throws(uint alignment)
    {
        GameHeap heap = CreateHeap(BootCursor);

        Assert.Throws<ArgumentOutOfRangeException>(() => heap.Allocate(64, alignment));
    }

    [Fact]
    public void Allocate_AdvancePassesSize_ReturnsZeroAndKeepsState()
    {
        GameHeap heap = CreateHeap(0x1000, Profile with { Size = 1000 });
        HeapState before = heap.Current;

        uint address = heap.Allocate(985, 16);

        Assert.Equal(0u, address);
        Assert.Equal(before, heap.Current);
        Assert.Null(heap.LastBlock);
    }

    [Fact]
    public void Allocate_AdvanceFillsSizeExactly_Succeeds()
    {
        GameHeap heap = CreateHeap(0x1000, Profile with { Size = 1000 });

        uint address = heap.Allocate(984, 16);

        Assert.Equal(0x1010u, address);
        Assert.Equal(1000u, heap.Current.Used);
    }

    [Fact]
    public void Allocate_WithUsedBytesAlreadyCounted_ChecksSizeAgainstUsedPlusAdvance()
    {
        var heap = new GameHeap(Profile with { Size = 1000 }, [new HeapState(0x1000, 3, 900)]);

        uint address = heap.Allocate(100, 16);

        Assert.Equal(0u, address);
    }

    [Fact]
    public void Constructor_States_ExposeDepthAndCurrentState()
    {
        HeapState[] states = [new(0x1000, 1, 100), new(0x2000, 2, 200), new(0x3000, 3, 300)];

        var heap = new GameHeap(Profile, states);

        Assert.Equal(2, heap.Depth);
        Assert.Equal(states[2], heap.Current);
        Assert.Equal(states, heap.States);
    }

    [Fact]
    public void Constructor_NoStates_Throws() =>
        Assert.Throws<ArgumentException>(() => new GameHeap(Profile, []));

    [Fact]
    public void Constructor_MoreStatesThanDepths_Throws()
    {
        HeapState[] states = [.. Enumerable.Repeat(new HeapState(0x1000, 0, 0), Profile.DepthCount + 1)];

        Assert.Throws<ArgumentException>(() => new GameHeap(Profile, states));
    }

    [Theory]
    [InlineData(1u, 4u)]
    [InlineData(5u, 8u)]
    [InlineData(8u, 8u)]
    [InlineData(4094u, 4096u)]
    public void Grow_Size_RoundsUpAndMovesCursorUsedAndBlockSize(uint size, uint rounded)
    {
        GameHeap heap = CreateHeap(BootCursor);
        uint address = heap.Allocate(100, 16);
        HeapState before = heap.Current;

        heap.Grow(size);

        Assert.Equal(new HeapState(before.Cursor + rounded, before.BlockCount, before.Used + rounded), heap.Current);
        Assert.Equal(new HeapBlock(address, 100 + rounded), heap.LastBlock);
    }

    [Fact]
    public void Grow_AfterBlockOfSizeNotAMultipleOfFour_ReturnsBlockEndNotCursor()
    {
        GameHeap heap = CreateHeap(BootCursor);
        uint address = heap.Allocate(101, 16);
        uint cursor = heap.Current.Cursor;

        uint end = heap.Grow(8);

        Assert.Equal(address + 101, end);
        Assert.Equal(address + 104, cursor);
    }

    [Fact]
    public void Grow_AfterBlockOfSizeAMultipleOfFour_ReturnsBlockEnd()
    {
        GameHeap heap = CreateHeap(BootCursor);
        uint address = heap.Allocate(256, 16);

        uint end = heap.Grow(64);

        Assert.Equal(address + 256, end);
    }

    [Fact]
    public void Grow_ConsecutiveGrows_EachReturnsTheEndTheLastLeft()
    {
        GameHeap heap = CreateHeap(BootCursor);
        uint address = heap.Allocate(256, 16);

        uint first = heap.Grow(76);
        uint second = heap.Grow(12);

        Assert.Equal(address + 256, first);
        Assert.Equal(address + 256 + 76, second);
    }

    [Fact]
    public void Grow_AdvancePassesSize_ReturnsZeroAndKeepsState()
    {
        GameHeap heap = CreateHeap(0x1000, Profile with { Size = 1000 });
        heap.Allocate(900, 16);
        HeapState before = heap.Current;
        HeapBlock? lastBlock = heap.LastBlock;

        uint end = heap.Grow(100);

        Assert.Equal(0u, end);
        Assert.Equal(before, heap.Current);
        Assert.Equal(lastBlock, heap.LastBlock);
    }

    [Fact]
    public void Grow_AdvanceFillsSizeExactly_Succeeds()
    {
        GameHeap heap = CreateHeap(0x1000, Profile with { Size = 1000 });
        uint address = heap.Allocate(900, 16);

        uint end = heap.Grow(84);

        Assert.Equal(address + 900, end);
        Assert.Equal(1000u, heap.Current.Used);
    }

    [Fact]
    public void Grow_NoLastBlock_Throws()
    {
        GameHeap heap = CreateHeap(BootCursor);

        Assert.Throws<InvalidOperationException>(() => heap.Grow(16));
    }

    [Fact]
    public void Push_CurrentState_StartsADepthWithACopyAndReturnsThePreviousDepth()
    {
        GameHeap heap = CreateHeap(BootCursor);
        heap.Allocate(64, 16);
        HeapState before = heap.Current;

        int from = heap.Push();

        Assert.Equal(0, from);
        Assert.Equal(1, heap.Depth);
        Assert.Equal(before, heap.Current);
        Assert.Equal(before, heap.States[0]);
    }

    [Fact]
    public void Push_AtTheDeepestDepth_Throws()
    {
        GameHeap heap = CreateHeap(BootCursor);
        for (int depth = 1; depth < Profile.DepthCount; depth++)
        {
            heap.Push();
        }

        Assert.Throws<InvalidOperationException>(() => heap.Push());
    }

    [Fact]
    public void Pop_ToTheDepthPushedFrom_RestoresItsFrozenState()
    {
        GameHeap heap = CreateHeap(BootCursor);
        heap.Allocate(64, 16);
        HeapState frozen = heap.Current;
        int from = heap.Push();
        heap.Allocate(128, 16);

        heap.Pop(from);

        Assert.Equal(from, heap.Depth);
        Assert.Equal(frozen, heap.Current);
    }

    [Fact]
    public void Pop_AfterBlocksAllocatedAtThePoppedDepth_ReusesTheirMemory()
    {
        GameHeap heap = CreateHeap(BootCursor);
        int from = heap.Push();
        uint first = heap.Allocate(256, 16);
        heap.Pop(from);

        uint second = heap.Allocate(256, 16);

        Assert.Equal(first, second);
    }

    [Fact]
    public void Pop_WhenLastBlockLiesAboveTheRestoredCursor_KeepsTheLastBlock()
    {
        GameHeap heap = CreateHeap(BootCursor);
        int from = heap.Push();
        uint address = heap.Allocate(256, 16);
        HeapBlock? lastBlock = heap.LastBlock;

        heap.Pop(from);

        Assert.True(address >= heap.Current.Cursor);
        Assert.Equal(lastBlock, heap.LastBlock);
    }

    [Fact]
    public void Pop_NestedDepths_OneAtATimeOrAllAtOnceReachTheSameState()
    {
        GameHeap stepwise = CreateHeap(BootCursor);
        GameHeap atOnce = CreateHeap(BootCursor);
        foreach (GameHeap heap in new[] { stepwise, atOnce })
        {
            heap.Allocate(64, 16);
            heap.Push();
            heap.Allocate(96, 32);
            heap.Push();
            heap.Allocate(160, 64);
        }

        stepwise.Pop(1);
        stepwise.Pop(0);
        atOnce.Pop(0);

        Assert.Equal(atOnce.States, stepwise.States);
        Assert.Equal(atOnce.LastBlock, stepwise.LastBlock);
    }

    [Fact]
    public void Pop_ToTheCurrentDepth_ChangesNothing()
    {
        GameHeap heap = CreateHeap(BootCursor);
        heap.Push();
        heap.Allocate(64, 16);
        HeapState before = heap.Current;

        heap.Pop(1);

        Assert.Equal(1, heap.Depth);
        Assert.Equal(before, heap.Current);
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(1)]
    [InlineData(5)]
    public void Pop_DepthOutsideZeroToCurrent_Throws(int depth)
    {
        GameHeap heap = CreateHeap(BootCursor);

        Assert.Throws<ArgumentOutOfRangeException>(() => heap.Pop(depth));
    }

    [Fact]
    public void Requests_OnAHeapBuiltFromCapturedState_ContinueExactlyAsTheOriginalDoes()
    {
        GameHeap original = CreateHeap(BootCursor);
        original.Allocate(1024, 16);
        original.Push();
        original.Allocate(101, 64);
        original.Grow(76);
        var captured = new GameHeap(Profile, original.States, original.LastBlock);

        uint[] fromOriginal = ContinueWith(original);
        uint[] fromCaptured = ContinueWith(captured);

        Assert.Equal(fromOriginal, fromCaptured);
        Assert.Equal(original.States, captured.States);
        Assert.Equal(original.LastBlock, captured.LastBlock);
    }

    private static uint[] ContinueWith(GameHeap heap)
    {
        uint grown = heap.Grow(12);
        uint first = heap.Allocate(2048, 16);
        heap.Push();
        uint second = heap.Allocate(33, 32);
        heap.Pop(1);
        uint third = heap.Allocate(40, 0);
        return [grown, first, second, third];
    }
}
