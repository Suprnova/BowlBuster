namespace BowlBuster.Chains.Vocabulary;

/// <summary>
/// A costume's preferred name, the character who wears it and the other names it is accepted under, such as an
/// abbreviation.
/// </summary>
public sealed class CostumeName
{
    /// <summary>
    /// Creates a costume name.
    /// </summary>
    /// <param name="preferred">The name BowlBuster prints, which is also accepted.</param>
    /// <param name="character">The character who wears the costume.</param>
    /// <param name="aliases">The other names accepted for the costume.</param>
    /// <exception cref="ArgumentException">A name is blank.</exception>
    public CostumeName(string preferred, Character character, params ReadOnlySpan<string> aliases)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(preferred);
        foreach (string alias in aliases) ArgumentException.ThrowIfNullOrWhiteSpace(alias);

        Preferred = preferred.Trim();
        Character = character;
        Aliases = [.. aliases.ToArray().Select(static alias => alias.Trim())];
    }

    /// <summary>
    /// The name BowlBuster prints.
    /// </summary>
    public string Preferred { get; }

    /// <summary>
    /// The character who wears the costume.
    /// </summary>
    public Character Character { get; }

    /// <summary>
    /// The other names accepted for the costume.
    /// </summary>
    public IReadOnlyList<string> Aliases { get; }
}
