using BowlBuster.Recordings;
using System.Buffers.Binary;

namespace BowlBuster.Landings;

/// <summary>
/// Names the object lookup table: <c>{id, base*}</c> slots of 8 bytes, named by the ID's asset.
/// </summary>
internal sealed class LookupTableNamer : IBlockNamer
{
    private const uint SlotSize = 8;

    public RegionName? Name(PlacedBlock block, uint offset, NamingContext context)
    {
        if (block.Size % SlotSize is not 0) return null;

        uint slot = offset / SlotSize;
        uint? id = context.Load?.Capture?.WordAt(block.Request.Address + (slot * SlotSize)) is { } word and not 0 ? word : null;
        return new LookupEntryName((int)slot, offset % SlotSize >= sizeof(uint), id, id is { } known ? context.FindAsset(known) : null);
    }
}

/// <summary>
/// Reads words from a capture.
/// </summary>
internal static class CaptureReads
{
    /// <summary>
    /// Reads a little-endian word.
    /// </summary>
    /// <returns>The word, or <see langword="null"/> when the capture doesn't hold it.</returns>
    public static uint? WordAt(this ILoadCapture capture, uint address)
    {
        Span<byte> value = stackalloc byte[sizeof(uint)];
        return capture.TryRead(address, value) ? BinaryPrimitives.ReadUInt32LittleEndian(value) : null;
    }

    /// <summary>
    /// Reads a byte.
    /// </summary>
    /// <returns>The byte, or <see langword="null"/> when the capture doesn't hold it.</returns>
    public static byte? ByteAt(this ILoadCapture capture, uint address)
    {
        Span<byte> value = stackalloc byte[1];
        return capture.TryRead(address, value) ? value[0] : null;
    }
}
