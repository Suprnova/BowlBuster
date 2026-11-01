using BowlBuster.Memory;
using BowlBuster.Recordings;

namespace BowlBuster.Replay;

/// <summary>
/// Why a recording was rejected: the first thing replay found that disagrees with it.
/// </summary>
/// <param name="Check">The check that failed.</param>
/// <param name="Site">Where in the recording, or <see langword="null"/> for a check on the whole run.</param>
/// <param name="Difference">
/// The values that disagree, the recorded one as <see cref="HeapDifference.Value"/> and the replayed one as
/// <see cref="HeapDifference.OtherValue"/>. It is <see langword="null"/> for a check that compares no value.
/// </param>
/// <param name="Detail">What a check that compares no value has to say.</param>
public sealed record ReplayMismatch(ReplayCheck Check, MismatchSite? Site, HeapDifference? Difference, string? Detail)
{
    /// <summary>
    /// Prints the mismatch on one line.
    /// </summary>
    /// <returns>The site, the check, and the values or detail.</returns>
    public override string ToString()
    {
        string? values = Difference is { } difference ? $"{difference.Field} recorded {Hex(difference.Value)}, replayed {Hex(difference.OtherValue)}" : null;
        string check = Site?.Request is { } request ? $"{Check} on {request}" : Check.ToString();

        return string.Join(": ", new[] { Site?.ToString(), check, values, Detail }.OfType<string>());
    }

    private static string Hex(uint? value) => value is { } known ? $"0x{known:X}" : "none";
}

/// <summary>
/// Where in a recording a <see cref="ReplayMismatch"/> was found.
/// </summary>
/// <param name="Segment">The segment's number.</param>
/// <param name="Load">The load.</param>
/// <param name="Op">The request's position in the load, or <see langword="null"/> for a check on the load as a whole.</param>
/// <param name="Heap">The replayed heap just before the failure.</param>
public readonly record struct MismatchSite(int Segment, RecordedLoad Load, int? Op, HeapSnapshot Heap)
{
    /// <summary>
    /// The request at <see cref="Op"/>, if any.
    /// </summary>
    public HeapRequest? Request => Op is { } op ? Load.Heap.Requests[op] : null;

    /// <summary>
    /// Prints the load and the op.
    /// </summary>
    /// <returns>The site, such as <c>ORIG (segment 0, counter 3), op 8</c>.</returns>
    public override string ToString()
    {
        string load = $"{Load.Key.Scene} (segment {Segment}, counter {Load.Counter})";
        return Op is { } op ? $"{load}, op {op}" : load;
    }
}
