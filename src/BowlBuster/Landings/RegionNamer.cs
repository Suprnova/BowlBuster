using BowlBuster.Platforms;

namespace BowlBuster.Landings;

/// <summary>
/// Names what a landing word lies in, with a namer per block kind chosen by the block's allocation site.
/// </summary>
/// <remarks>
/// A class-1 archive layer is named down to its asset, padding or slack from the disc, and a live object array down to
/// the object, its asset and its field from the load's capture. Any other block, or a block its namer can't tell, is an
/// unknown region named by its caller: a wrong guess is worse than an unknown.
/// </remarks>
/// <param name="profile">The platform's constants.</param>
/// <param name="layers">The archive layers on disc, or <see langword="null"/> when there are none to read.</param>
public sealed class RegionNamer(PlatformProfile profile, ILayerSource? layers)
{
    private readonly Dictionary<uint, IBlockNamer> namers = profile.Live.Sites
        .Select(site => KeyValuePair.Create<uint, IBlockNamer>(site.Caller, new LiveObjectNamer(profile.Live, site)))
        .Append(KeyValuePair.Create<uint, IBlockNamer>(profile.Sites.ArchiveLayer, new LayerNamer()))
        .ToDictionary();

    /// <summary>
    /// Names the block a word's first byte lies in.
    /// </summary>
    /// <param name="region">What the word's first byte lies in.</param>
    /// <param name="load">The load that allocated the block, or <see langword="null"/> when nothing is known of it.</param>
    /// <returns>The name, or <see langword="null"/> outside a live block.</returns>
    public RegionName? Name(LandingRegion region, LoadContext? load)
    {
        if (region is not { Kind: RegionKind.Block, Block: { } block }) return null;

        return namers.TryGetValue(block.Request.Caller, out IBlockNamer? namer)
            && namer.Name(block, region.Offset, new NamingContext(layers, load)) is { } name
            ? name
            : new UnknownRegionName(block.Request.Caller);
    }
}
