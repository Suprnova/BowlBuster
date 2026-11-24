using BowlBuster.Landings;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Tests.Recordings;

namespace BowlBuster.Tests.Landings;

public class TableNamersTests
{
    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;
    private const uint Objects = 0x700000;
    private const uint Table = 0x701000;
    private const byte CounterType = 0x16;
    private const uint CounterSize = 0x1C;

    private static readonly LiveType Counter = Platform.Live.Find(CounterType)!;

    /// <summary>Three counters, IDs <c>0x100</c>, <c>0x200</c> and <c>0x300</c>, below a table of up to four slots or entries.</summary>
    private static ByteCapture Capture()
    {
        ByteCapture capture = new(Objects, Table + 0x20 - Objects);
        for (uint index = 0; index < 3; index++)
            capture.Word(Objects + (index * CounterSize) + 4, (index + 1) * 0x100).Byte(Objects + (index * CounterSize) + 8, CounterType);
        return capture;
    }

    private static PlacedBlock Block(uint address, uint size, uint caller, int position = 0) =>
        new(position, 0, address - 0xC, address, size, new AllocRequest(size, 0x10, address, caller));

    private static readonly PlacedBlock Counters = Block(Objects, 3 * CounterSize, 0x68F3B);

    private static RegionName? Name(PlacedBlock table, uint offset, ILoadCapture? capture) =>
        new RegionNamer(Platform, null).Name(new LandingRegion(RegionKind.Block, table, offset), new LoadContext(capture, []), [Counters, table]);

    private static PlacedBlock Lookup(uint size = 0x20) => Block(Table, size, Platform.Sites.LookupTable);

    private static PlacedBlock Bases(uint size = 0xC) => Block(Table, size, 0x74014);

    [Theory]
    [InlineData(0x8u, 1, false)]
    [InlineData(0xFu, 1, true)]
    [InlineData(0x1Cu, 3, true)]
    public void Name_InTheLookupTable_NamesTheSlotAndItsHalf(uint offset, int slot, bool isPointer)
    {
        var name = Assert.IsType<LookupEntryName>(Name(Lookup(), offset, Capture().Word(Table + 8, 0x200).Word(Table + 0x18, 0x400)));

        Assert.Equal((slot, isPointer), (name.Slot, name.IsPointer));
        Assert.Equal(NamingDepth.Field, name.Depth);
    }

    [Fact]
    public void Name_LookupSlotWithAnId_HoldsTheId() =>
        Assert.Equal(new LookupEntryName(1, false, 0x200, null), Name(Lookup(), 0x8, Capture().Word(Table + 8, 0x200)));

    [Fact]
    public void Name_EmptyLookupSlot_HasNoId() =>
        Assert.Equal(new LookupEntryName(2, false, null, null), Name(Lookup(), 0x10, Capture()));

    [Fact]
    public void Name_LookupTableWithoutACapture_HasSlotsButNoIds() =>
        Assert.Equal(new LookupEntryName(1, true, null, null), Name(Lookup(), 0xC, null));

    [Fact]
    public void Name_LookupTableThatIsntWholeSlots_IsUnknown() =>
        Assert.Equal(new UnknownRegionName(Platform.Sites.LookupTable), Name(Lookup(0x1C), 0x8, Capture()));

    [Fact]
    public void Name_BaseEntry_NamesWhatItPointsAt()
    {
        var name = Assert.IsType<PointerEntryName>(Name(Bases(), 0x5, Capture().Word(Table + 4, Objects + CounterSize)));

        Assert.Equal(("bases", 1), (name.Array, name.Entry));
        Assert.Equal(new LiveObjectName(Counter, 1, 0x200, null, 0, Counter.FieldAt(0)), name.Target);
    }

    [Theory]
    [InlineData(0u)]
    [InlineData(Objects + (3 * CounterSize))]
    public void Name_BaseEntryPointingAtNoLiveBlock_HasNoTarget(uint target) =>
        Assert.Equal(new PointerEntryName("bases", 0, null), Name(Bases(), 0, Capture().Word(Table, target)));

    [Fact]
    public void Name_BaseEntryPointingAtItsOwnArray_HasNoTarget() =>
        Assert.Equal(new PointerEntryName("bases", 0, null), Name(Bases(), 0, Capture().Word(Table, Table + 4)));

    [Fact]
    public void Name_BaseArrayWithoutACapture_HasEntriesButNoTargets() =>
        Assert.Equal(new PointerEntryName("bases", 2, null), Name(Bases(), 0x8, null));

    [Fact]
    public void BlockAt_AnEarlierLoadsBlockOverTheSameRecordedAddress_IsNotTheLoads()
    {
        PlacedBlock earlier = Block(Objects, 0x1000, 0x72670, position: 0) with { Address = 0x600000 };
        PlacedBlock later = Block(Objects + 0x800, 0x100, 0x68F3B, position: 1);
        NamingContext context = new(null, null, [earlier, later], []);

        Assert.Equal(later, context.BlockAt(1, Objects + 0x810));
        Assert.Null(context.BlockAt(1, Objects + 0x10));
        Assert.Equal(earlier, context.BlockAt(0, Objects + 0x10));
    }
}
