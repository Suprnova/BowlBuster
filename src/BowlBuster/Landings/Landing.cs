using BowlBuster.Platforms;

namespace BowlBuster.Landings;

/// <summary>
/// Where a load's stale write falls and what lies under it, resolved against the heap as it stood at the load's cutoff.
/// </summary>
/// <param name="Sphere">The stale pointer the load writes through.</param>
/// <param name="PlayerEntity">The address of the player entity this load leaked, which names the player's lookup entry.</param>
/// <param name="Heap">The heap at the cutoff.</param>
/// <param name="Words">Every field the write stores and the render path reads, in the footprint's order.</param>
public sealed record Landing(SphereAssignment Sphere, uint? PlayerEntity, LandingHeap Heap, IReadOnlyList<LandingWord> Words)
{
    /// <summary>
    /// Finds the word at an offset from the stale pointer.
    /// </summary>
    /// <param name="offset">The offset.</param>
    /// <returns>The word, or <see langword="null"/> when the footprint has none there.</returns>
    public LandingWord? WordAt(uint offset) => Words
        .Where(word => word.Word.Offset == offset)
        .Select(static word => (LandingWord?)word)
        .FirstOrDefault();
}

/// <summary>
/// The value of the stale sphere pointer.
/// </summary>
/// <param name="Position">The position in the chain of the load that set it.</param>
/// <param name="Address">The sphere instance's simulated address.</param>
public readonly record struct SphereAssignment(int Position, uint Address);

/// <summary>
/// The heap at a load's cutoff.
/// </summary>
/// <param name="Top">The highest end of anything the load had allocated. The whole footprint above it is memory no live object uses.</param>
/// <param name="Cursor">The cursor.</param>
/// <param name="Depth">The depth.</param>
public readonly record struct LandingHeap(uint Top, uint Cursor, int Depth);

/// <summary>
/// One field of the footprint, resolved.
/// </summary>
/// <param name="Word">The field.</param>
/// <param name="Address">The field's simulated address.</param>
/// <param name="Region">What its first byte lies in.</param>
/// <param name="Original">The bytes there before the write, or <see langword="null"/> when nothing holds them.</param>
/// <param name="IsVolatile">Whether the game rebuilds these bytes every frame, so a capture can't say what a later frame holds.</param>
public readonly record struct LandingWord(FootprintWord Word, uint Address, LandingRegion Region, OriginalBytes? Original, bool IsVolatile);

/// <summary>
/// The bytes a field held before the write. They are as the recording's run held them, so a pointer among them is in that
/// run's frame, not the simulation's.
/// </summary>
/// <param name="Value">The field's value, little-endian.</param>
/// <param name="Source">Where the bytes came from.</param>
/// <param name="RecordedAddress">The field's address in the recording's run, which is the reference to the bytes.</param>
public readonly record struct OriginalBytes(uint Value, ByteSource Source, uint RecordedAddress);

/// <summary>
/// Where a field's original bytes came from.
/// </summary>
public enum ByteSource
{
    /// <summary>
    /// The load's capture: live memory at the cutoff.
    /// </summary>
    Capture,

    /// <summary>
    /// The archive layer's image on disc, which lacks anything the game fixes up at load time.
    /// </summary>
    Disk,
}
