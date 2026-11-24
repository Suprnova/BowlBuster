using BowlBuster.Platforms;
using BowlBuster.Recordings;
using System.Buffers.Binary;

namespace BowlBuster.Landings;

/// <summary>
/// Reads what a field held before the stale write.
/// </summary>
/// <remarks>
/// A capture is addressed as its own run saw it, so a block is read at its recorded address plus the offset, and one
/// capture serves a load at every shift. Bytes the capture doesn't hold come from the archive layer on disc.
/// <para>
/// Only a live block has original bytes. A gap's size depends on the phase, and its bytes are stale memory or a header
/// written for other addresses, while memory above the heap isn't in a capture at all. A word that runs past its block's
/// end has no original bytes either, since the rest of it isn't the block's.
/// </para>
/// <para>
/// The bone matrices of a model are rebuilt every frame, so a capture from the first frame doesn't hold what a later
/// frame will. They are never read from one.
/// </para>
/// </remarks>
/// <param name="profile">The platform's constants.</param>
/// <param name="layers">The archive layers on disc, or <see langword="null"/> when there are none to read.</param>
public sealed class OriginalBytesReader(PlatformProfile profile, ILayerSource? layers)
{
    /// <summary>
    /// Reads a field's original bytes.
    /// </summary>
    /// <param name="region">What the field's first byte lies in.</param>
    /// <param name="word">The field.</param>
    /// <param name="capture">The capture of the load that placed the block, if it has one.</param>
    /// <returns>The bytes, or <see langword="null"/> when nothing holds them, and whether the game rebuilds them every frame.</returns>
    public (OriginalBytes? Original, bool IsVolatile) Read(LandingRegion region, FootprintWord word, ILoadCapture? capture)
    {
        if (region is not { Kind: RegionKind.Block, Block: { } block }) return (null, false);

        if (IsVolatile(block, region.Offset)) return (null, true);

        if (region.Offset + (uint)word.Size > block.Size) return (null, false);

        uint recordedAddress = block.Request.Address + region.Offset;
        Span<byte> bytes = stackalloc byte[sizeof(uint)];
        Span<byte> field = bytes[..word.Size];

        if (capture?.TryRead(recordedAddress, field) is true)
            return (new OriginalBytes(BinaryPrimitives.ReadUInt32LittleEndian(bytes), ByteSource.Capture, recordedAddress), false);

        if (block.Request.Layer is { } layer && layers?.TryRead(layer, block.Size, region.Offset, field) is true)
            return (new OriginalBytes(BinaryPrimitives.ReadUInt32LittleEndian(bytes), ByteSource.Disk, recordedAddress), false);

        return (null, false);
    }

    private bool IsVolatile(PlacedBlock block, uint offset)
    {
        ModelPoolProfile pools = profile.Pools;

        if (block.Request.Caller == profile.Sites.ModelInstance) return offset + pools.InstanceSize < block.Size;

        return block.Request.Caller == profile.Sites.ModelPool
            && pools.ShapeOfSize(block.Size) is { } shape
            && offset < pools.MatrixBytes(shape);
    }
}

