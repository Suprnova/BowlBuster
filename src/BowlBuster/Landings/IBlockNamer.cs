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
/// <param name="Live">The live blocks, in address order, which a pointer in a block resolves against.</param>
/// <param name="BootArchives">The archives the game loaded at boot, where an ID the load's own archives lack is looked up.</param>
internal sealed record NamingContext(ILayerSource? Layers, LoadContext? Load, IReadOnlyList<PlacedBlock> Live, IReadOnlyList<string> BootArchives)
{
    /// <summary>
    /// Finds an object's asset by its ID: in the load's archives, then in the boot archives.
    /// </summary>
    public AssetRef? FindAsset(uint id) => Layers is null ? null
        : Layers.FindAsset(Load?.Archives ?? [], id) ?? Layers.FindAsset(BootArchives, id);

    /// <summary>
    /// Finds the live block of a load that holds an address of the recording's run.
    /// </summary>
    /// <remarks>
    /// <see cref="Live"/> is in address order, and a later load's blocks lie above an earlier one's, so ordering by
    /// position and then recorded address keeps the list's order.
    /// </remarks>
    /// <param name="position">The load's position.</param>
    /// <param name="recorded">The address, as the load's recording saw it.</param>
    public PlacedBlock? BlockAt(int position, uint recorded)
    {
        int low = 0;
        int high = Live.Count - 1;
        while (low <= high)
        {
            int middle = low + ((high - low) / 2);
            if ((Live[middle].Position, Live[middle].Request.Address).CompareTo((position, recorded)) <= 0) low = middle + 1;
            else high = middle - 1;
        }

        return high >= 0 && Live[high] is { } block && block.Position == position && recorded < block.Request.Address + block.Size
            ? block
            : null;
    }
}

/// <summary>
/// Names a class-1 archive layer's block from the disc.
/// </summary>
internal sealed class LayerNamer : IBlockNamer
{
    public RegionName? Name(PlacedBlock block, uint offset, NamingContext context) =>
        block.Request.Layer is { } layer ? context.Layers?.Name(layer, block.Size, offset) : null;
}
