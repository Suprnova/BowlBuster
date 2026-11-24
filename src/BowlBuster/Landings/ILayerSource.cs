using BowlBuster.Recordings;

namespace BowlBuster.Landings;

/// <summary>
/// The archive layers on disc, as the game maps them into a heap block.
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
}
