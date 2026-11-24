using BowlBuster.Landings;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Tests.Recordings;

namespace BowlBuster.Tests.Landings;

public class AssetDirectoryNamerTests
{
    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;
    private const uint Address = 0x700000;
    private const uint RecordSize = 0x60;

    private static readonly AssetRef[] Scene = [new(0x10, "a", "Counter"), new(0x20, "b", "Counter")];
    private static readonly AssetRef[] Costume = [new(0x30, "c", "Model"), new(0x40, "d", "Model")];
    private static readonly AssetRef[] Menu = [new(0x50, "e", "Text")];

    private static RegionName? Name(uint offset, IReadOnlyList<string> archives, ILoadCapture? capture = null, uint size = 2 * RecordSize, ILayerSource? disc = null, LayerId? layer = null)
    {
        PlacedBlock block = new(0, 0, Address - 0xC, Address, size, new AllocRequest(size, 0x40, Address, Platform.Sites.ArchiveLayer, layer));
        return new RegionNamer(Platform, disc ?? new Directories()).Name(new LandingRegion(RegionKind.Block, block, offset), new LoadContext(capture, archives), []);
    }

    [Fact]
    public void Name_TheOneArchiveWhoseAssetsFillTheBlock_NamesTheRecordsAssetAndField() =>
        Assert.Equal(
            new AssetDirectoryName("SCENE", 1, Scene[1], 0x34, Platform.Live.DirectoryRecord.FieldAt(0x34)),
            Name(RecordSize + 0x34, ["MENU", "SCENE"]));

    [Fact]
    public void Name_BytesNoFieldCovers_ReachTheAsset()
    {
        var name = Assert.IsType<AssetDirectoryName>(Name(0x10, ["SCENE"]));

        Assert.Null(name.Field);
        Assert.Equal(NamingDepth.Identity, name.Depth);
    }

    [Fact]
    public void Name_NoArchiveOfThatSize_IsUnknown() =>
        Assert.Equal(new UnknownRegionName(Platform.Sites.ArchiveLayer), Name(0, ["MENU"]));

    [Fact]
    public void Name_TwoArchivesOfThatSize_TheCapturesFirstIdChooses() =>
        Assert.Equal("COSTUME", Assert.IsType<AssetDirectoryName>(Name(0, ["SCENE", "COSTUME"], new ByteCapture(Address, 2 * RecordSize).Word(Address, 0x30))).Archive);

    [Fact]
    public void Name_TwoArchivesOfThatSizeWithoutACapture_IsUnknown() =>
        Assert.Equal(new UnknownRegionName(Platform.Sites.ArchiveLayer), Name(0, ["SCENE", "COSTUME"]));

    [Fact]
    public void Name_WithoutADisc_IsUnknown()
    {
        PlacedBlock block = new(0, 0, Address - 0xC, Address, 2 * RecordSize, new AllocRequest(2 * RecordSize, 0x40, Address, Platform.Sites.ArchiveLayer));

        RegionName? name = new RegionNamer(Platform, null).Name(new LandingRegion(RegionKind.Block, block, 0), new LoadContext(null, ["SCENE"]), []);

        Assert.Equal(new UnknownRegionName(Platform.Sites.ArchiveLayer), name);
    }

    [Fact]
    public void Name_BlockTheDiscNamesAsALayer_StaysALayer()
    {
        LayerAssetName layer = new(new LayerId("SCENE", 0), Scene[0], 0);

        Assert.Equal(layer, Name(0, ["SCENE"], disc: new Directories(layer), layer: layer.Layer));
    }

    private sealed class Directories(RegionName? layer = null) : ILayerSource
    {
        public bool TryRead(LayerId layer, uint blockSize, uint offset, Span<byte> destination) => false;

        public RegionName? Name(LayerId layerId, uint blockSize, uint offset) => layer;

        public AssetRef? FindAsset(IReadOnlyList<string> archives, uint id) => null;

        public IReadOnlyList<AssetRef>? DirectoryOf(string archive) => archive switch
        {
            "SCENE" => Scene,
            "COSTUME" => Costume,
            "MENU" => Menu,
            _ => null,
        };
    }
}
