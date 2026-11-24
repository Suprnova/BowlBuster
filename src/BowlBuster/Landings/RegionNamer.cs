using BowlBuster.Platforms;
using BowlBuster.Recordings;

namespace BowlBuster.Landings;

/// <summary>
/// Names what a landing word lies in, with a namer per block kind chosen by the block's allocation site.
/// </summary>
/// <remarks>
/// A class-1 archive layer is named down to its asset, padding or slack from the disc. Any other block, or a block its
/// namer can't tell, is an unknown region named by its caller: a wrong guess is worse than an unknown.
/// </remarks>
/// <param name="profile">The platform's constants.</param>
/// <param name="layers">The archive layers on disc, or <see langword="null"/> when there are none to read.</param>
public sealed class RegionNamer(PlatformProfile profile, ILayerSource? layers)
{
    private readonly Dictionary<uint, IBlockNamer> namers = new()
    {
        [profile.Sites.ArchiveLayer] = new LayerNamer(),
    };

    /// <summary>
    /// Names the block a word's first byte lies in.
    /// </summary>
    /// <param name="region">What the word's first byte lies in.</param>
    /// <param name="capture">The capture of the load that allocated the block, or <see langword="null"/> when it has none.</param>
    /// <returns>The name, or <see langword="null"/> outside a live block.</returns>
    public RegionName? Name(LandingRegion region, ILoadCapture? capture)
    {
        if (region is not { Kind: RegionKind.Block, Block: { } block }) return null;

        return namers.TryGetValue(block.Request.Caller, out IBlockNamer? namer)
            && namer.Name(block, region.Offset, new NamingContext(layers, capture)) is { } name
            ? name
            : new UnknownRegionName(block.Request.Caller);
    }
}
