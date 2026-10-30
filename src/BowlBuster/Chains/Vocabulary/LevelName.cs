namespace BowlBuster.Chains.Vocabulary;

/// <summary>
/// A level's preferred name and the other names it is accepted under, such as its scene tag.
/// </summary>
public sealed class LevelName
{
    /// <summary>
    /// Creates a level name.
    /// </summary>
    /// <param name="preferred">The name BowlBuster prints, which is also accepted.</param>
    /// <param name="aliases">The other names accepted for the level.</param>
    /// <exception cref="ArgumentException">A name is blank.</exception>
    public LevelName(string preferred, params ReadOnlySpan<string> aliases)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(preferred);
        foreach (string alias in aliases) ArgumentException.ThrowIfNullOrWhiteSpace(alias);

        Preferred = preferred.Trim();
        Aliases = [.. aliases.ToArray().Select(static alias => alias.Trim())];
    }

    /// <summary>
    /// The name BowlBuster prints.
    /// </summary>
    public string Preferred { get; }

    /// <summary>
    /// The other names accepted for the level.
    /// </summary>
    public IReadOnlyList<string> Aliases { get; }
}
