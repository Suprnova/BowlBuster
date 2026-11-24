using BowlBuster.Recordings;

namespace BowlBuster.Landings;

/// <summary>
/// What is known of the load that allocated a block, beyond its requests.
/// </summary>
/// <param name="Capture">The load's capture at its cutoff, or <see langword="null"/> when it has none.</param>
/// <param name="Archives">The archives the load mapped layers of into the heap, in the order it loaded them, which are where its objects' assets are.</param>
public sealed record LoadContext(ILoadCapture? Capture, IReadOnlyList<string> Archives)
{
    /// <summary>
    /// The context of a recorded load.
    /// </summary>
    /// <param name="heap">What the load did to the heap.</param>
    /// <param name="capture">The load's capture at its cutoff, or <see langword="null"/> when it has none.</param>
    public static LoadContext Of(HeapLog heap, ILoadCapture? capture)
    {
        ArgumentNullException.ThrowIfNull(heap);
        return new(capture, [.. heap.Requests.OfType<AllocRequest>().Select(static alloc => alloc.Layer?.Archive).OfType<string>().Distinct()]);
    }
}
