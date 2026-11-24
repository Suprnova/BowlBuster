using BowlBuster.Chains;
using BowlBuster.Discs;
using BowlBuster.Loads;
using BowlBuster.Memory;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using EvilHop;
using EvilHop.Assets;
using EvilHop.Common;
using EvilHop.Serialization;

namespace BowlBuster.Tests.Discs;

public sealed class LayerCheckTests : IDisposable
{
    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;
    private const uint BlockAddress = 0x100000;
    private const uint BlockSize = 0x800;
    private const string CaptureId = "cutoff";

    private readonly DirectoryInfo disc = Directory.CreateTempSubdirectory("bowlbuster-layers-");
    private readonly byte[] image;

    public LayerCheckTests()
    {
        var archive = Archive.Create(Serializer.Create(GameVersion.TSSM, EvilHop.Common.Platform.Xbox));
        using (var session = archive.OpenAssets())
        {
            var layer = session.CreateLayer(LayerType.Default);
            layer.Add(new CounterAsset { Id = new AssetId(1), Name = "first", InitialValue = 3 });
            layer.Add(new CounterAsset { Id = new AssetId(2), Name = "second" });
        }

        Directory.CreateDirectory(Path.Combine(disc.FullName, "MN"));
        using (var stream = File.Create(Path.Combine(disc.FullName, "MN", "MNUI.HIP")))
            archive.Save(stream);

        using var reread = File.OpenRead(Path.Combine(disc.FullName, "MN", "MNUI.HIP"));
        image = Archive.Load(reread, GameVersion.TSSM, EvilHop.Common.Platform.Xbox).ReadAssets().GetLayerImage(0).ToArray();
    }

    public void Dispose() => disc.Delete(recursive: true);

    private static Recording RecordingOf(AllocRequest request, Cutoff? cutoff)
    {
        var start = new HeapSnapshot([new HeapState(BlockAddress - 0x10, 0, 0)], null);
        var load = new RecordedLoad(new LoadKey("MNUI", Costumes.None), 2, null, new HeapLog(start, [request], cutoff, false));
        return new Recording("synthetic-1", "xbox", CounterBasis.Retail, 0, [new RecordingSegment(0, [load])]);
    }

    private static AllocRequest LayerBlock(int layer = 0, uint caller = 0) =>
        new(BlockSize, 0x40, BlockAddress, caller == 0 ? Platform.Sites.ArchiveLayer : caller, new LayerId("MN\\MNUI", layer));

    private LayerComparison Compare(Recording recording, byte[]? captured = null) =>
        new LayerCheck(Platform, new DiscLayers(disc.FullName, Platform), new MemoryCaptures(BlockAddress, captured ?? image))
            .Compare(recording)
            .Single();

    [Fact]
    public void Compare_CaptureHoldingTheImage_IsTheSame()
    {
        var comparison = Compare(RecordingOf(LayerBlock(), new Cutoff(1, CaptureId)));

        Assert.Equal(LayerMatch.Same, comparison.Match);
        Assert.Empty(comparison.Differences);
        Assert.Equal((0, 0, new LayerId("MN\\MNUI", 0), BlockAddress, BlockSize), (comparison.Segment, comparison.Op, comparison.Layer, comparison.Address, comparison.Size));
    }

    [Fact]
    public void Compare_CaptureWithOneWordChanged_NamesTheWordByItsAsset()
    {
        byte[] captured = [.. image];
        captured[0x18] ^= 0xFF;

        var comparison = Compare(RecordingOf(LayerBlock(), new Cutoff(1, CaptureId)), captured);

        Assert.Equal(LayerMatch.Differs, comparison.Match);
        var word = Assert.Single(comparison.Differences);
        Assert.Equal((0x18u, "second", 8u), (word.Offset, word.Asset, word.OffsetInAsset));
        Assert.Equal(BitConverter.ToUInt32(captured, 0x18), word.Captured);
        Assert.Equal(BitConverter.ToUInt32(image, 0x18), word.OnDisc);
    }

    [Fact]
    public void Compare_WordInThePaddingBetweenAssets_HasNoAsset()
    {
        byte[] captured = [.. image];
        captured[0xC] ^= 0xFF;

        var word = Assert.Single(Compare(RecordingOf(LayerBlock(), new Cutoff(1, CaptureId)), captured).Differences);

        Assert.Equal((0xCu, (string?)null, 0u), (word.Offset, word.Asset, word.OffsetInAsset));
    }

    [Fact]
    public void Compare_LayerTheDiscDoesntHave_IsNotOnDisc() =>
        Assert.Equal(LayerMatch.NotOnDisc, Compare(RecordingOf(LayerBlock(layer: 4), new Cutoff(1, CaptureId))).Match);

    [Theory]
    [InlineData(0, CaptureId)]
    [InlineData(1, null)]
    [InlineData(1, "missing")]
    public void Compare_BlockNoCaptureHolds_IsNotCaptured(int requestsBeforeCapture, string? captureId) =>
        Assert.Equal(LayerMatch.NotCaptured, Compare(RecordingOf(LayerBlock(), new Cutoff(requestsBeforeCapture, captureId))).Match);

    [Fact]
    public void Compare_LoadWithNoCutoff_IsNotCaptured() =>
        Assert.Equal(LayerMatch.NotCaptured, Compare(RecordingOf(LayerBlock(), null)).Match);

    [Fact]
    public void Compare_BlocksFromOtherCallers_AreLeftOut()
    {
        var check = new LayerCheck(Platform, new DiscLayers(disc.FullName, Platform), new MemoryCaptures(BlockAddress, image));

        Assert.Empty(check.Compare(RecordingOf(LayerBlock(caller: 0x197916), new Cutoff(1, CaptureId))));
    }

    private sealed class MemoryCaptures(uint start, byte[] bytes) : ICaptureSource
    {
        public ILoadCapture? Find(string recordingId, string captureId) => captureId == CaptureId ? new Capture(start, bytes) : null;

        private sealed class Capture(uint start, byte[] bytes) : ILoadCapture
        {
            public uint HeapTop => start + (uint)bytes.Length;

            public bool TryRead(uint address, Span<byte> destination)
            {
                if (address < start || address + (uint)destination.Length > HeapTop) return false;
                bytes.AsSpan((int)(address - start), destination.Length).CopyTo(destination);
                return true;
            }
        }
    }
}
