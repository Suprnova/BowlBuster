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
}
