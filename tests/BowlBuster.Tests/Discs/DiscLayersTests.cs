using BowlBuster.Discs;
using BowlBuster.Landings;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using EvilHop;
using EvilHop.Assets;
using EvilHop.Common;
using EvilHop.Serialization;

namespace BowlBuster.Tests.Discs;

public sealed class DiscLayersTests : IDisposable
{
    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;

    /// <summary>Two 12-byte Counters 16 bytes apart: a 28-byte image in a <c>0x800</c>-byte block.</summary>
    private const uint ImageLength = 28;
    private const uint BlockSize = 0x800;

    private readonly DirectoryInfo disc = Directory.CreateTempSubdirectory("bowlbuster-disc-");
    private readonly DiscLayers layers;

    public DiscLayersTests()
    {
        WriteArchive("MN/mnui.HIP", initialValue: 3);
        WriteArchive("B1/b101.HOP", initialValue: 5);
        layers = new DiscLayers(disc.FullName, Platform);
    }

    public void Dispose() => disc.Delete(recursive: true);

    private void WriteArchive(string path, short initialValue)
    {
        var archive = Archive.Create(Serializer.Create(GameVersion.TSSM, EvilHop.Common.Platform.Xbox));
        using (var session = archive.OpenAssets())
        {
            var layer = session.CreateLayer(LayerType.Default);
            layer.Add(new CounterAsset { Id = new AssetId(1), Name = "first", InitialValue = initialValue });
            layer.Add(new CounterAsset { Id = new AssetId(2), Name = "second" });
        }

        string file = Path.Combine(disc.FullName, path);
        Directory.CreateDirectory(Path.GetDirectoryName(file)!);
        using var stream = File.Create(file);
        archive.Save(stream);
    }

    private short? InitialValue(LayerId layer, uint blockSize = BlockSize)
    {
        Span<byte> bytes = stackalloc byte[2];
        return layers.TryRead(layer, blockSize, 8, bytes) ? BitConverter.ToInt16(bytes) : null;
    }

    [Fact]
    public void TryRead_HipNamedWithoutItsExtension_ReadsTheLayersImage() =>
        Assert.Equal((short)3, InitialValue(new LayerId("MN\\MNUI", 0)));

    [Fact]
    public void TryRead_HopNamedWithItsExtension_ReadsTheLayersImage() =>
        Assert.Equal((short)5, InitialValue(new LayerId("B1\\B101.HOP", 0)));

    [Fact]
    public void TryRead_NameInAnotherCase_Resolves() =>
        Assert.Equal((short)3, InitialValue(new LayerId("mn\\MnUi", 0)));

    [Theory]
    [InlineData("MN\\MNUS")]
    [InlineData("XX\\MNUI")]
    [InlineData("MN\\MNUI.HOP")]
    public void TryRead_ArchiveNotOnTheDisc_IsFalse(string archive) =>
        Assert.Null(InitialValue(new LayerId(archive, 0)));

    [Theory]
    [InlineData(-1)]
    [InlineData(1)]
    public void TryRead_LayerTheArchiveDoesntHave_IsFalse(int layer) =>
        Assert.Null(InitialValue(new LayerId("MN\\MNUI", layer)));

    [Theory]
    [InlineData(0x600u)]
    [InlineData(0x1000u)]
    [InlineData(ImageLength)]
    public void TryRead_BlockOfAnotherSize_IsFalse(uint blockSize) =>
        Assert.Null(InitialValue(new LayerId("MN\\MNUI", 0), blockSize));

    [Fact]
    public void TryRead_TheImagesLastBytes_AreRead()
    {
        Span<byte> bytes = stackalloc byte[4];

        Assert.True(layers.TryRead(new LayerId("MN\\MNUI", 0), BlockSize, ImageLength - 4, bytes));
    }

    [Theory]
    [InlineData(ImageLength - 2)]
    [InlineData(ImageLength)]
    [InlineData(BlockSize - 4)]
    public void TryRead_PastTheImagesEnd_IsFalse(uint offset)
    {
        Span<byte> bytes = stackalloc byte[4];

        Assert.False(layers.TryRead(new LayerId("MN\\MNUI", 0), BlockSize, offset, bytes));
    }

    [Fact]
    public void TryRead_ArchiveAskedForTwice_AnswersBothTimes()
    {
        Assert.Equal((short)3, InitialValue(new LayerId("MN\\MNUI", 0)));

        Assert.Equal((short)3, InitialValue(new LayerId("MN\\MNUI", 0)));
    }

    [Fact]
    public void Read_ThroughTheDisc_GivesDiskBytes()
    {
        var request = new AllocRequest(BlockSize, 0x40, 0x700000, Platform.Sites.ArchiveLayer, new LayerId("MN\\MNUI", 0));
        var block = new PlacedBlock(0, 0, 0x6FFFF4, 0x710000, BlockSize, request);
        var reader = new OriginalBytesReader(Platform, layers);

        var (original, _) = reader.Read(new LandingRegion(RegionKind.Block, block, 8), new FootprintWord(8, 2, null), capture: null);

        Assert.Equal(new OriginalBytes(3, ByteSource.Disk, 0x700008), original);
    }

    private static readonly LayerId Mnui = new("MN\\MNUI", 0);
    private static readonly AssetRef First = new(1, "first", nameof(AssetType.Counter));
    private static readonly AssetRef Second = new(2, "second", nameof(AssetType.Counter));

    [Theory]
    [InlineData(0u, true)]
    [InlineData(3u, true)]
    [InlineData(8u, false)]
    public void Name_InAnAsset_NamesItAndTheOffsetInIt(uint offset, bool firstWord)
    {
        var name = Assert.IsType<LayerAssetName>(layers.Name(Mnui, BlockSize, offset));

        Assert.Equal(new LayerAssetName(Mnui, First, offset), name);
        Assert.Equal(firstWord, name.IsFirstWord);
    }

    [Fact]
    public void Name_InTheSecondAsset_CountsFromItsStart() =>
        Assert.Equal(new LayerAssetName(Mnui, Second, 4), layers.Name(Mnui, BlockSize, 20));

    [Fact]
    public void Name_InThePaddingBetweenAssets_NamesBoth() =>
        Assert.Equal(new LayerPaddingName(Mnui, First, Second, 2), layers.Name(Mnui, BlockSize, 14));

    [Theory]
    [InlineData(ImageLength, 0u)]
    [InlineData(BlockSize - 1, BlockSize - 1 - ImageLength)]
    public void Name_PastTheImageInTheBlock_IsTheSlack(uint offset, uint pastEnd) =>
        Assert.Equal(new LayerSlackName(Mnui, Second, pastEnd), layers.Name(Mnui, BlockSize, offset));

    [Fact]
    public void Name_PastTheBlock_IsNull() =>
        Assert.Null(layers.Name(Mnui, BlockSize, BlockSize));

    [Fact]
    public void Name_BlockThatIsntTheLayer_IsNull()
    {
        Assert.Null(layers.Name(Mnui, 0x600, 0));
        Assert.Null(layers.Name(new LayerId("MN\\MNUS", 0), BlockSize, 0));
    }

    [Fact]
    public void Constructor_PlatformWithNoEvilHopPlatform_ThrowsArgumentException() =>
        Assert.Throws<ArgumentException>(() => new DiscLayers(disc.FullName, Platform with { Platform = "gamecube" }));
}
