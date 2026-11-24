namespace BowlBuster.Landings;

/// <summary>
/// Names what a landing word lies in. A class-1 archive layer is named down to its asset, padding or slack from the
/// disc; any other block, or a layer with no disc to read, is an unknown region named by its caller.
/// </summary>
/// <param name="layers">The archive layers on disc, or <see langword="null"/> when there are none to read.</param>
public sealed class RegionNamer(ILayerSource? layers)
{
    /// <summary>
    /// Names the block a word's first byte lies in.
    /// </summary>
    /// <param name="region">What the word's first byte lies in.</param>
    /// <returns>The name, or <see langword="null"/> outside a live block.</returns>
    public RegionName? Name(LandingRegion region)
    {
        if (region is not { Kind: RegionKind.Block, Block: { } block }) return null;

        return block.Request.Layer is { } layer && layers?.Name(layer, block.Size, region.Offset) is { } name
            ? name
            : new UnknownRegionName(block.Request.Caller);
    }
}
