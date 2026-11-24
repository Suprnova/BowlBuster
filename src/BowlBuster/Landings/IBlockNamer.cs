namespace BowlBuster.Landings;

/// <summary>
/// Names inside the blocks of one kind, which <see cref="RegionNamer"/> picks by the block's allocation site.
/// </summary>
internal interface IBlockNamer
{
    /// <summary>
    /// Names what lies at an offset of a block.
    /// </summary>
    /// <param name="block">The block.</param>
    /// <param name="offset">The offset in the block.</param>
    /// <param name="context">What the namer may read.</param>
    /// <returns>The name, or <see langword="null"/> when the namer can't tell, which leaves the block an unknown region.</returns>
    RegionName? Name(PlacedBlock block, uint offset, NamingContext context);
}

/// <summary>
/// What a block namer may read.
/// </summary>
/// <param name="Layers">The archive layers on disc, or <see langword="null"/> when there are none to read.</param>
/// <param name="Load">The load that allocated the block, or <see langword="null"/> when nothing is known of it.</param>
internal sealed record NamingContext(ILayerSource? Layers, LoadContext? Load);

/// <summary>
/// Names a class-1 archive layer's block from the disc.
/// </summary>
internal sealed class LayerNamer : IBlockNamer
{
    public RegionName? Name(PlacedBlock block, uint offset, NamingContext context) =>
        block.Request.Layer is { } layer ? context.Layers?.Name(layer, block.Size, offset) : null;
}
