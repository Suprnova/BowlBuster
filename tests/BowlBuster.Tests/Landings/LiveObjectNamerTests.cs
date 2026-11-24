using BowlBuster.Landings;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Tests.Recordings;

namespace BowlBuster.Tests.Landings;

public class LiveObjectNamerTests
{
    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;
    private const uint ArraySite = 0x68F3B;
    private const uint PlayerSite = 0x69081;
    private const uint Address = 0x700000;
    private const byte CounterType = 0x16;
    private const string Scene = "XX\\SCENE";

    private static readonly LiveType Counter = Platform.Live.Find(CounterType)!;
    private static readonly AssetRef SceneAsset = new(0x100, "scene counter", "Counter");
    private static readonly AssetRef BootAsset = new(0x300, "boot counter", "Counter");

    /// <summary>Three counters: IDs <c>0x100</c>, 0 and <c>0x300</c>.</summary>
    private static ByteCapture Counters() => new ByteCapture(Address, 3 * 0x1C)
        .Word(Address + 0x4, 0x100).Byte(Address + 0x8, CounterType)
        .Byte(Address + 0x1C + 0x8, CounterType)
        .Word(Address + 0x38 + 0x4, 0x300).Byte(Address + 0x38 + 0x8, CounterType);

    private static RegionName? Name(uint offset, ILoadCapture? capture, uint caller = ArraySite, uint size = 3 * 0x1C, ILayerSource? layers = null)
    {
        PlacedBlock block = new(0, 0, Address - 0xC, Address, size, new AllocRequest(size, 0x10, Address, caller));
        return new RegionNamer(Platform, layers).Name(new LandingRegion(RegionKind.Block, block, offset), new LoadContext(capture, [Scene]), []);
    }

    [Fact]
    public void Name_InALiveObject_NamesTheTypeElementIdAndField() =>
        Assert.Equal(new LiveObjectName(Counter, 2, 0x300, null, 0x18, Counter.FieldAt(0x18)), Name(0x38 + 0x18, Counters()));

    [Fact]
    public void Name_ObjectWithIdZero_HasNoId()
    {
        var name = Assert.IsType<LiveObjectName>(Name(0x1C + 0x4, Counters()));

        Assert.Null(name.Id);
        Assert.Equal("id", name.Field?.Name);
    }

    [Fact]
    public void Name_OffsetNoFieldCovers_ReachesTheObject()
    {
        var name = Assert.IsType<LiveObjectName>(Name(0x1B, Counters()));

        Assert.Null(name.Field);
        Assert.Equal(NamingDepth.Identity, name.Depth);
    }

    [Fact]
    public void Name_ObjectWhoseTypeByteDisagrees_IsUnknown() =>
        Assert.Equal(new UnknownRegionName(ArraySite), Name(0x1C + 0x18, Counters().Byte(Address + 0x1C + 0x8, 0x0E)));

    [Fact]
    public void Name_FirstObjectsTypeNoTableHas_IsUnknown() =>
        Assert.Equal(new UnknownRegionName(ArraySite), Name(0x18, Counters().Byte(Address + 0x8, 0xFF)));

    [Fact]
    public void Name_BlockThatIsntAWholeNumberOfObjects_IsUnknown() =>
        Assert.Equal(new UnknownRegionName(ArraySite), Name(0x18, Counters(), size: 3 * 0x1C - 4));

    [Fact]
    public void Name_ArrayWithoutACapture_IsUnknown() =>
        Assert.Equal(new UnknownRegionName(ArraySite), Name(0x18, null));

    [Fact]
    public void Name_PlayerArrayWithoutACapture_TakesTheSitesType()
    {
        LiveType player = Platform.Live.Find(0x03)!;

        var name = Assert.IsType<LiveObjectName>(Name(0x18, null, PlayerSite, player.Size));

        Assert.Equal(new LiveObjectName(player, 0, null, null, 0x18, null), name);
        Assert.Equal(NamingDepth.Element, name.Depth);
    }

    [Fact]
    public void Name_PlayerArrayThatHoldsNoTypeByte_StillTakesTheSitesType() =>
        Assert.IsType<LiveObjectName>(Name(0x18, new ByteCapture(Address, 0xE0), PlayerSite, 0xE0));

    [Theory]
    [InlineData(0x18u, 0x100u)]
    [InlineData(0x38u + 0x18, 0x300u)]
    public void Name_ObjectsAsset_IsFoundInTheLoadsArchivesThenAtBoot(uint offset, uint id)
    {
        AssetLayers disc = new(new() { [(Scene, 0x100)] = SceneAsset, [("boot", 0x300)] = BootAsset, [("boot", 0x100)] = BootAsset });

        var name = Assert.IsType<LiveObjectName>(Name(offset, Counters(), layers: disc));

        Assert.Equal(id is 0x100 ? SceneAsset : BootAsset, name.Asset);
    }

    private sealed class AssetLayers(Dictionary<(string Archive, uint Id), AssetRef> assets) : ILayerSource
    {
        public bool TryRead(LayerId layer, uint blockSize, uint offset, Span<byte> destination) => false;

        public RegionName? Name(LayerId layer, uint blockSize, uint offset) => null;

        public AssetRef? FindAsset(IReadOnlyList<string> archives, uint id) => archives
            .Select(archive => assets.TryGetValue((archive, id), out AssetRef asset) ? asset : (AssetRef?)null)
            .FirstOrDefault(static asset => asset is not null);

        public IReadOnlyList<AssetRef>? DirectoryOf(string archive) => null;
    }
}
