using BowlBuster.Landings;
using BowlBuster.Platforms;
using BowlBuster.Recordings;

namespace BowlBuster.Tests.Landings;

public class RegionNamerTests
{
    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;
    private static readonly LayerId Layer = new("TARG", 0);
    private static readonly RegionName Named = new LayerAssetName(Layer, new AssetRef(1, "asset", "Counter"), 4);

    private static PlacedBlock Block(uint caller, LayerId? layer = null) =>
        new(0, 0, 0x6FFFF4, 0x700000, 0x800, new AllocRequest(0x800, 0x40, 0x700000, caller, layer));

    [Fact]
    public void Name_LayerBlockTheSourceNames_IsTheSourcesName() =>
        Assert.Equal(Named, new RegionNamer(new NamingLayers(Named)).Name(new LandingRegion(RegionKind.Block, Block(Platform.Sites.ArchiveLayer, Layer), 4)));

    [Fact]
    public void Name_LayerBlockTheSourceDoesntName_IsUnknownByCaller() =>
        Assert.Equal(new UnknownRegionName(Platform.Sites.ArchiveLayer), new RegionNamer(new NamingLayers(null)).Name(new LandingRegion(RegionKind.Block, Block(Platform.Sites.ArchiveLayer, Layer), 4)));

    [Fact]
    public void Name_LayerBlockWithNoDisc_IsUnknownByCaller() =>
        Assert.Equal(new UnknownRegionName(Platform.Sites.ArchiveLayer), new RegionNamer(null).Name(new LandingRegion(RegionKind.Block, Block(Platform.Sites.ArchiveLayer, Layer), 4)));

    [Fact]
    public void Name_BlockWithNoLayer_IsUnknownByCaller() =>
        Assert.Equal(new UnknownRegionName(0x72670), new RegionNamer(new NamingLayers(Named)).Name(new LandingRegion(RegionKind.Block, Block(0x72670), 4)));

    [Theory]
    [InlineData(RegionKind.Header)]
    [InlineData(RegionKind.Padding)]
    [InlineData(RegionKind.Freed)]
    [InlineData(RegionKind.AboveHeap)]
    public void Name_OutsideALiveBlock_IsNull(RegionKind kind) =>
        Assert.Null(new RegionNamer(new NamingLayers(Named)).Name(new LandingRegion(kind, Block(Platform.Sites.ArchiveLayer, Layer), 4)));

    private sealed class NamingLayers(RegionName? name) : ILayerSource
    {
        public bool TryRead(LayerId layer, uint blockSize, uint offset, Span<byte> destination) => false;

        public RegionName? Name(LayerId layer, uint blockSize, uint offset) => name;
    }
}
