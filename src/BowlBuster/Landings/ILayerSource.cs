using BowlBuster.Recordings;

namespace BowlBuster.Landings;

/// <summary>
/// The archives on disc: their layers, as the game maps them into a heap block, and their assets.
/// </summary>
/// <remarks>
/// An asset directory comes from the same allocator as a layer and carries the same identity, so an implementation must
/// check that the block is the layer before answering.
/// </remarks>
public interface ILayerSource
{
    /// <summary>
    /// Reads bytes from a layer's image.
    /// </summary>
    /// <param name="layer">The layer the loader was loading.</param>
    /// <param name="blockSize">The size of the heap block.</param>
    /// <param name="offset">The offset in the block.</param>
    /// <param name="destination">Receives the bytes.</param>
    /// <returns><see langword="true"/> when the block is that layer and the image holds every byte asked for.</returns>
    bool TryRead(LayerId layer, uint blockSize, uint offset, Span<byte> destination);

    /// <summary>
    /// Names what lies at an offset of a layer's block: an asset, the padding between two, or the slack past the last.
    /// </summary>
    /// <param name="layer">The layer the loader was loading.</param>
    /// <param name="blockSize">The size of the heap block.</param>
    /// <param name="offset">The offset in the block.</param>
    /// <returns>The name, or <see langword="null"/> when the block isn't that layer or the offset is past its end.</returns>
    RegionName? Name(LayerId layer, uint blockSize, uint offset);

    /// <summary>
    /// Finds an asset by its ID in the first of some archives that has it.
    /// </summary>
    /// <param name="archives">The archives to look in, named as a recording names them.</param>
    /// <param name="id">The asset's ID.</param>
    /// <returns>The asset, or <see langword="null"/> when none of the archives that resolve has it.</returns>
    AssetRef? FindAsset(IReadOnlyList<string> archives, uint id);

    /// <summary>
    /// Lists an archive's assets in the order of its asset directory, which is ascending ID.
    /// </summary>
    /// <param name="archive">The archive, named as a recording names it.</param>
    /// <returns>The assets, or <see langword="null"/> when the archive doesn't resolve.</returns>
    IReadOnlyList<AssetRef>? DirectoryOf(string archive);
}
