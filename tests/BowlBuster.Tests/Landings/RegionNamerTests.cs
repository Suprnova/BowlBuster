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

    private static RegionName? Name(ILayerSource? layers, LandingRegion region) => new RegionNamer(Platform, layers).Name(region, null);

    [Fact]
    public void Name_LayerBlockTheSourceNames_IsTheSourcesName() =>
        Assert.Equal(Named, Name(new NamingLayers(Named), new LandingRegion(RegionKind.Block, Block(Platform.Sites.ArchiveLayer, Layer), 4)));

    [Fact]
    public void Name_LayerBlockTheSourceDoesntName_IsUnknownByCaller() =>
        Assert.Equal(new UnknownRegionName(Platform.Sites.ArchiveLayer), Name(new NamingLayers(null), new LandingRegion(RegionKind.Block, Block(Platform.Sites.ArchiveLayer, Layer), 4)));

    [Fact]
    public void Name_LayerBlockWithNoDisc_IsUnknownByCaller() =>
        Assert.Equal(new UnknownRegionName(Platform.Sites.ArchiveLayer), Name(null, new LandingRegion(RegionKind.Block, Block(Platform.Sites.ArchiveLayer, Layer), 4)));

    [Fact]
    public void Name_BlockWithNoLayer_IsUnknownByCaller() =>
        Assert.Equal(new UnknownRegionName(0x72670), Name(new NamingLayers(Named), new LandingRegion(RegionKind.Block, Block(0x72670), 4)));

    [Fact]
    public void Name_LayerIdentityFromAnotherSite_IsUnknownByCaller() =>
        Assert.Equal(new UnknownRegionName(0x74031), Name(new NamingLayers(Named), new LandingRegion(RegionKind.Block, Block(0x74031, Layer), 4)));

    [Theory]
    [InlineData(RegionKind.Header)]
    [InlineData(RegionKind.Padding)]
    [InlineData(RegionKind.Freed)]
    [InlineData(RegionKind.AboveHeap)]
    public void Name_OutsideALiveBlock_IsNull(RegionKind kind) =>
        Assert.Null(Name(new NamingLayers(Named), new LandingRegion(kind, Block(Platform.Sites.ArchiveLayer, Layer), 4)));

    internal sealed class NamingLayers(RegionName? name) : ILayerSource
    {
        public bool TryRead(LayerId layer, uint blockSize, uint offset, Span<byte> destination) => false;

        public RegionName? Name(LayerId layer, uint blockSize, uint offset) => name;
    }
}
