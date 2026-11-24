using BowlBuster.Landings;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Tests.Recordings;
using static BowlBuster.Tests.Recordings.ScriptedScenes;

namespace BowlBuster.Tests.Landings;

public class NamingCoverageTests
{
    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;
    private static readonly RegionName Named = new LayerAssetName(new LayerId("ORIG", 0), new AssetRef(1, "asset", "Counter"), 0);

    private static IReadOnlyList<LoadNaming> Measure(ScriptedGame game, ILayerSource? layers) =>
        new NamingCoverage(Platform, new RegionNamer(Platform, layers), new FakeCaptures(game.CaptureTops)).Measure(game.Recording);

    private static ScriptedGame OriginCaptured() => new ScriptedGame(OriginStart).Run(Origin, 3, capture: "origin-cutoff");

    [Fact]
    public void Measure_LoadWithoutACapture_IsLeftOut()
    {
        ScriptedGame game = new ScriptedGame(OriginStart).Run(Origin, 3).Run(Target, 4, capture: "target-cutoff");

        IReadOnlyList<LoadNaming> loads = Measure(game, null);

        Assert.Equal(["TARG"], loads.Select(static load => load.Load.Key.Scene));
    }

    [Fact]
    public void Measure_CapturedLoad_ListsItsBlocksLiveAtTheCutoffInAddressOrder()
    {
        IReadOnlyList<BlockNaming> blocks = Measure(OriginCaptured(), null).Single().Blocks;

        Assert.Equal([EntitySite, LayerSite, PoolSite, PoolSite, PoolSite, LayerSite], blocks.Select(static block => block.Block.Request.Caller));
        Assert.Equal(blocks.OrderBy(static block => block.Block.Address), blocks);
    }

    [Fact]
    public void Measure_LayerBlockTheDiscNames_CountsEveryByteAtTheNamesDepth()
    {
        BlockNaming layer = Measure(OriginCaptured(), new RegionNamerTests.NamingLayers(Named)).Single().Blocks[^1];

        Assert.Equal(Named, layer.First);
        Assert.Equal(new Dictionary<NamingDepth, uint> { [NamingDepth.Identity] = 0x2100 }, layer.Bytes);
    }

    [Fact]
    public void Measure_BlockNoNamerNames_IsUnknownByCallerThroughout()
    {
        BlockNaming layer = Measure(OriginCaptured(), null).Single().Blocks[1];

        Assert.Equal(new UnknownRegionName(LayerSite), layer.First);
        Assert.Equal(new Dictionary<NamingDepth, uint> { [NamingDepth.Caller] = 0x10000 }, layer.Bytes);
    }
}
