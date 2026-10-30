namespace BowlBuster.Chains;

/// <summary>
/// The origin or the target of a chain: one load of a level, in the costumes that matter there.
/// </summary>
public sealed record LevelStep
{
    /// <summary>
    /// Creates a level step.
    /// </summary>
    /// <param name="level">The level, as written.</param>
    /// <param name="costumes">The costumes worn, or <see langword="null"/> when they don't matter.</param>
    /// <exception cref="ArgumentException"><paramref name="level"/> is blank.</exception>
    public LevelStep(string level, Costumes? costumes = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(level);

        Level = level;
        Costumes = costumes ?? Costumes.None;
    }

    /// <summary>
    /// The level, as written.
    /// </summary>
    public string Level { get; }

    /// <summary>
    /// The costumes worn, which are <see cref="Costumes.None"/> when they don't matter.
    /// </summary>
    public Costumes Costumes { get; }

    /// <summary>
    /// Prints the level, followed by its costumes in parentheses when any matter.
    /// </summary>
    /// <returns>The step.</returns>
    public override string ToString() => Costumes.IsEmpty ? Level : $"{Level} ({Costumes})";
}
