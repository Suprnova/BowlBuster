namespace BowlBuster.Chains;

/// <summary>
/// A run of filler loads between a chain's origin and its target: levels that add loads without giving SpongeBob a new
/// bowl pointer. Each takes its own write. Fillers carry no costumes.
/// </summary>
public sealed record FillerStep
{
    /// <summary>
    /// Creates a run of filler loads.
    /// </summary>
    /// <param name="level">The level loaded each time, or <see langword="null"/> for any non-SpongeBob levels.</param>
    /// <param name="count">The number of loads, 1 or more.</param>
    /// <exception cref="ArgumentException"><paramref name="level"/> is blank.</exception>
    /// <exception cref="ArgumentOutOfRangeException"><paramref name="count"/> is below 1.</exception>
    public FillerStep(string? level, int count)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(count, 1);
        if (level is not null) ArgumentException.ThrowIfNullOrWhiteSpace(level);

        Level = level;
        Count = count;
    }

    /// <summary>
    /// The level loaded each time, or <see langword="null"/> for any non-SpongeBob levels.
    /// </summary>
    public string? Level { get; }

    /// <summary>
    /// The number of loads, 1 or more.
    /// </summary>
    public int Count { get; }

    /// <summary>
    /// Prints "non-SB xN" for any levels, and the level for a named one, followed by " xN" when it repeats.
    /// </summary>
    /// <returns>The step.</returns>
    public override string ToString() => Level switch
    {
        null => $"non-SB x{Count}",
        _ when Count > 1 => $"{Level} x{Count}",
        _ => Level,
    };
}
