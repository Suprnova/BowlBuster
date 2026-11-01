using BowlBuster.Chains;
using BowlBuster.Landings;
using BowlBuster.Loads;
using BowlBuster.Memory;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Replay;
using BowlBuster.Simulation;
using BowlBuster.Tests.Recordings;
using BowlBuster.Tests.Simulation;

namespace BowlBuster.Tests.Landings;

public class OriginalBytesTests
{
    private const int OriginRecordedAt = 2;
    private const int TargetRecordedAt = 3;

    private const string TargetCapture = "target-cutoff";

    private const uint TargetLayer = 0x738700;
    private const uint TargetLayerGrownSize = 0x60040;
    private const uint ScaleOffsetInLayer = 0x2AD4;

    private const uint PoolSize = 72_588;
    private const uint PoolMatrixBytes = 0x5100;
    private const uint InstanceSize = 0xA0;

    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;

    private static readonly LoadKey OriginKey = new("ORIG", Costumes.None);
    private static readonly LoadKey TargetKey = new("TARG", Costumes.None);

    private static readonly FootprintWord FourBytes = new(0x58, 4, 0x40833333);

    private readonly ValidatedRecording origin = Recorded(ScriptedScenes.Origin, OriginRecordedAt, ScriptedScenes.OriginStart);
    private readonly ValidatedRecording target = Recorded(ScriptedScenes.Target, TargetRecordedAt, ScriptedScenes.TargetStart, TargetCapture);
    private readonly SpyCapture capture = new(0x800000);
    private readonly OriginalBytesReader reader = new(Platform, null);

    private static ValidatedRecording Recorded(Scene scene, int load, HeapSnapshot start, string? captureId = null) =>
        RecordingLibraryTests.Validated(new ScriptedGame(start, scene.Name).Run(scene, load + 1, capture: captureId).Recording);

    private static uint LittleEndian(uint address, int size) =>
        Enumerable.Range(0, size).Aggregate(0u, (value, index) => value | ((uint)FakeCapture.ByteAt(address + (uint)index) << (8 * index)));

    private static PlacedBlock Block(uint address, uint size, uint caller, LayerId? layer = null) =>
        new(0, 0, address - 12, address + 0x1000, size, new AllocRequest(size, 16, address, caller, layer));

    private static LandingRegion InBlock(PlacedBlock block, uint offset) => new(RegionKind.Block, block, offset);

    private ChainSimulator Simulator(IReadOnlyDictionary<string, uint>? tops = null, ILayerImageSource? layers = null) => new(
        Platform,
        new RecordingLibrary([origin, target]),
        new FakeCaptures(tops ?? new Dictionary<string, uint> { [TargetCapture] = 0x79876C }),
        layers);

    private static Landing LandingOf(ChainSimulator simulator, int originLoad) =>
        simulator.Simulate(new ChainPlan(new LoadNumber(originLoad), [OriginKey, TargetKey])).Loads[1].Landing!;

    [Theory]
    [InlineData(OriginRecordedAt)]
    [InlineData(OriginRecordedAt + 3)]
    public void Original_AtAnyShift_ReadsTheBlocksRecordedAddress(int originLoad)
    {
        const uint recordedAddress = TargetLayer + ScaleOffsetInLayer;

        OriginalBytes? original = LandingOf(Simulator(), originLoad).WordAt(0x58)?.Original;

        Assert.Equal(new OriginalBytes(LittleEndian(recordedAddress, 4), ByteSource.Capture, recordedAddress), original);
    }

    [Fact]
    public void Original_AtAShift_IsNotTheSimulatedAddressesBytes()
    {
        LandingWord word = Assert.NotNull(LandingOf(Simulator(), OriginRecordedAt + 3).WordAt(0x58));

        Assert.NotEqual(word.Address, word.Original?.RecordedAddress);
    }

    [Theory]
    [InlineData(0x4Cu, 2, 0x73B1C8u)]
    [InlineData(0x4Eu, 1, 0x73B1CAu)]
    public void Original_ShorterFields_TakeOnlyTheirOwnBytes(uint offset, int size, uint recordedAddress)
    {
        OriginalBytes? original = LandingOf(Simulator(), OriginRecordedAt).WordAt(offset)?.Original;

        Assert.Equal(LittleEndian(recordedAddress, size), original?.Value);
    }

    [Fact]
    public void Original_NoCaptureButALayer_ComesFromDiskWithTheBlocksSize()
    {
        FakeLayers layers = new();
        Dictionary<string, uint> none = [];

        OriginalBytes? original = LandingOf(Simulator(none, layers), OriginRecordedAt).WordAt(0x58)?.Original;

        Assert.Equal(ByteSource.Disk, original?.Source);
        Assert.Equal(FakeLayers.ValueAt(ScaleOffsetInLayer), original?.Value);
        Assert.Equal(new LayerId("TARG", 0), layers.LastLayer);
        Assert.Equal(TargetLayerGrownSize, layers.LastBlockSize);
    }

    [Fact]
    public void Original_CaptureThatStopsBelowTheAddress_FallsBackToDisk()
    {
        Dictionary<string, uint> tooShort = new() { [TargetCapture] = 0x700000 };

        OriginalBytes? original = LandingOf(Simulator(tooShort, new FakeLayers()), OriginRecordedAt).WordAt(0x58)?.Original;

        Assert.Equal(ByteSource.Disk, original?.Source);
    }

    [Fact]
    public void Original_NoCaptureNoLayers_IsNull()
    {
        Dictionary<string, uint> none = [];

        Assert.All(LandingOf(Simulator(none), OriginRecordedAt).Words, static word => Assert.Null(word.Original));
    }

    [Fact]
    public void Read_BlockWithNoLayerAndNoCapture_IsNull()
    {
        PlacedBlock block = Block(0x700000, 0x100, 0x590B0);

        (OriginalBytes? original, bool isVolatile) = new OriginalBytesReader(Platform, new FakeLayers()).Read(InBlock(block, 0x10), FourBytes, null);

        Assert.Null(original);
        Assert.False(isVolatile);
    }

    [Fact]
    public void Read_LayerSourceRefusingTheBlock_IsNull()
    {
        PlacedBlock directory = Block(0x700000, 0x600, Platform.Sites.ArchiveLayer, new LayerId("TARG", 0));
        FakeLayers refusing = new() { Refuses = true };

        (OriginalBytes? original, _) = new OriginalBytesReader(Platform, refusing).Read(InBlock(directory, 0x10), FourBytes, null);

        Assert.Null(original);
    }

    [Theory]
    [InlineData(RegionKind.Header)]
    [InlineData(RegionKind.Padding)]
    [InlineData(RegionKind.Freed)]
    [InlineData(RegionKind.AboveHeap)]
    public void Read_AnythingButALiveBlock_HasNoOriginalAndReadsNothing(RegionKind kind)
    {
        PlacedBlock block = Block(0x700000, 0x100, 0x590B0, new LayerId("TARG", 0));

        (OriginalBytes? original, bool isVolatile) = reader.Read(new LandingRegion(kind, block, 0x10), FourBytes, capture);

        Assert.Null(original);
        Assert.False(isVolatile);
        Assert.Equal(0, capture.Reads);
    }

    [Theory]
    [InlineData(0xFDu)]
    [InlineData(0x100u)]
    public void Read_WordRunningPastTheBlocksEnd_HasNoOriginal(uint offset)
    {
        PlacedBlock block = Block(0x700000, 0x100, 0x590B0);

        (OriginalBytes? original, _) = reader.Read(InBlock(block, offset), FourBytes, capture);

        Assert.Null(original);
        Assert.Equal(0, capture.Reads);
    }

    [Fact]
    public void Read_WordEndingAtTheBlocksEnd_IsRead()
    {
        PlacedBlock block = Block(0x700000, 0x100, 0x590B0);

        (OriginalBytes? original, _) = reader.Read(InBlock(block, 0xFC), FourBytes, capture);

        Assert.NotNull(original);
    }

    [Theory]
    [InlineData(0u)]
    [InlineData(PoolMatrixBytes - 4)]
    public void Read_PoolMatrices_AreVolatileAndNeverRead(uint offset)
    {
        PlacedBlock pool = Block(0x700000, PoolSize, Platform.Sites.ModelPool);

        (OriginalBytes? original, bool isVolatile) = reader.Read(InBlock(pool, offset), FourBytes, capture);

        Assert.Null(original);
        Assert.True(isVolatile);
        Assert.Equal(0, capture.Reads);
    }

    [Theory]
    [InlineData(PoolMatrixBytes)]
    [InlineData(PoolMatrixBytes + 0xC)]
    [InlineData(PoolSize - 4)]
    public void Read_PoolHeaderAndInstances_AreNotVolatile(uint offset)
    {
        PlacedBlock pool = Block(0x700000, PoolSize, Platform.Sites.ModelPool);

        (OriginalBytes? original, bool isVolatile) = reader.Read(InBlock(pool, offset), FourBytes, capture);

        Assert.NotNull(original);
        Assert.False(isVolatile);
    }

    [Fact]
    public void Read_BlockFromThePoolSiteOfNoPoolsSize_IsNotVolatile()
    {
        PlacedBlock block = Block(0x700000, PoolSize + 4, Platform.Sites.ModelPool);

        Assert.False(reader.Read(InBlock(block, 0), FourBytes, capture).IsVolatile);
    }

    [Theory]
    [InlineData(0u, true)]
    [InlineData(0x7Cu, true)]
    [InlineData(0x80u, false)]
    [InlineData(0x11Cu, false)]
    public void Read_StandaloneInstance_HasVolatileMatricesAndAStableInstance(uint offset, bool expected)
    {
        const uint twoMatrices = 0x80;
        PlacedBlock instance = Block(0x700000, twoMatrices + InstanceSize, Platform.Sites.ModelInstance);

        Assert.Equal(expected, reader.Read(InBlock(instance, offset), FourBytes, capture).IsVolatile);
    }

    [Fact]
    public void Original_BlockFromAnEarlierLoad_ReadsThatLoadsCapture()
    {
        const string holderCapture = "holder-cutoff";
        Scene holder = new(
            "HOLD",
            [
                new Alloc(ScriptedScenes.EntitySize, 0, ScriptedScenes.EntitySite),
                new Alloc(0x60000, 0x40, ScriptedScenes.PlaySite),
                new CutoffHere(),
                new ExitScene(),
            ]);
        ChainSimulator simulator = new(
            Platform,
            new RecordingLibrary([origin, target, Recorded(holder, TargetRecordedAt, ScriptedScenes.TargetStart, holderCapture)]),
            new FakeCaptures(new Dictionary<string, uint> { [holderCapture] = 0x800000, [TargetCapture] = 0x700000 }));

        ChainResult result = simulator.Simulate(new ChainPlan(new LoadNumber(OriginRecordedAt), [OriginKey, new LoadKey("HOLD", Costumes.None), TargetKey]));

        LandingWord word = Assert.NotNull(result.Loads[2].Landing?.WordAt(0x58));
        Assert.Equal(RegionKind.Block, word.Region.Kind);
        Assert.Equal(1, word.Region.Block?.Position);
        Assert.Equal(ByteSource.Capture, word.Original?.Source);
    }

    private sealed class SpyCapture(uint top) : ILoadCapture
    {
        private readonly FakeCapture inner = new(top);

        public int Reads { get; private set; }

        public uint HeapTop => inner.HeapTop;

        public bool TryRead(uint address, Span<byte> destination)
        {
            Reads++;
            return inner.TryRead(address, destination);
        }
    }

    private sealed class FakeLayers : ILayerImageSource
    {
        public bool Refuses { get; init; }

        public LayerId? LastLayer { get; private set; }

        public uint LastBlockSize { get; private set; }

        public static uint ValueAt(uint offset) => offset ^ 0x5A5A5A5A;

        public bool TryRead(LayerId layer, uint blockSize, uint offset, Span<byte> destination)
        {
            LastLayer = layer;
            LastBlockSize = blockSize;

            if (Refuses) return false;

            BitConverter.TryWriteBytes(destination, ValueAt(offset));
            return true;
        }
    }
}
