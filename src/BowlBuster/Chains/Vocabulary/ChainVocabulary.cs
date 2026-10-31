namespace BowlBuster.Chains.Vocabulary;

/// <summary>
/// The names a chain may be written in, and the preferred name each resolves to. Every name is accepted without regard
/// to case or surrounding spaces; a chain only ever holds and prints the preferred names.
/// </summary>
/// <remarks>
/// A name with no entry is kept as written. A level then prints as it was written, and a costume can only be placed by
/// its position when both costumes are written.
/// </remarks>
public sealed class ChainVocabulary
{
    private readonly Dictionary<string, LevelName> levels;
    private readonly Dictionary<string, CostumeName> costumes;

    /// <summary>
    /// Creates a vocabulary.
    /// </summary>
    /// <param name="levels">The levels with their names.</param>
    /// <param name="costumes">The costumes with their names.</param>
    /// <exception cref="ArgumentException">A name is used by more than one level, or by more than one costume.</exception>
    public ChainVocabulary(IEnumerable<LevelName> levels, IEnumerable<CostumeName> costumes)
    {
        ArgumentNullException.ThrowIfNull(levels);
        ArgumentNullException.ThrowIfNull(costumes);

        this.levels = Index(levels, static level => level.Preferred, static level => level.Aliases);
        this.costumes = Index(costumes, static costume => costume.Preferred, static costume => costume.Aliases);
    }

    /// <summary>
    /// The costumes known from the game, with the abbreviations runners use.
    /// </summary>
    public static IReadOnlyList<CostumeName> KnownCostumes { get; } =
    [
        new CostumeName("Plain Sponge", Character.Spongebob, "PS"),
        new CostumeName("Mermaid Man", Character.Spongebob, "MM"),
        new CostumeName("Ripped Pants", Character.Spongebob, "RPS"),
        new CostumeName("Caveman Sponge", Character.Spongebob, "CMS"),
        new CostumeName("Plain Patrick", Character.Patrick, "PP"),
        new CostumeName("Disco Patrick", Character.Patrick, "DP"),
        new CostumeName("Caveman Patrick", Character.Patrick, "CMP"),
        new CostumeName("Goofy Goober", Character.Patrick, "GGP"),
    ];

    /// <summary>
    /// The known costumes and no levels, until the labels file supplies them.
    /// </summary>
    public static ChainVocabulary Default { get; } = new([], KnownCostumes);

    /// <summary>
    /// Resolves a level to its preferred name.
    /// </summary>
    /// <param name="text">The level as written.</param>
    /// <returns>The level's preferred name, or <paramref name="text"/> trimmed when the level has no entry.</returns>
    public string ResolveLevel(string text)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(text);
        return levels.TryGetValue(text.Trim(), out LevelName? level) ? level.Preferred : text.Trim();
    }

    /// <summary>
    /// Resolves the costumes written for a level to their preferred names, placed by character: SpongeBob's first, then
    /// Patrick's.
    /// </summary>
    /// <param name="written">The one or two costumes as written.</param>
    /// <returns>The costumes.</returns>
    /// <exception cref="ArgumentException">There are not one or two costumes.</exception>
    /// <exception cref="FormatException">
    /// A lone costume has no entry, so its character is unknown; a costume is written in the wrong position; or both
    /// belong to the same character.
    /// </exception>
    public Costumes ResolveCostumes(IReadOnlyList<string> written)
    {
        ArgumentNullException.ThrowIfNull(written);
        if (written.Count is not (1 or 2)) throw new ArgumentException("A level has one or two costumes.", nameof(written));

        if (written.Count is 1)
        {
            string text = written[0].Trim();
            CostumeName costume = costumes.GetValueOrDefault(text)
                ?? throw new FormatException($"The costume '{text}' is not known, so its character can't be told. Write both costumes, SpongeBob's first.");

            return costume.Character is Character.Spongebob ? new Costumes(costume.Preferred, null) : new Costumes(null, costume.Preferred);
        }

        return new Costumes(Place(written[0], Character.Spongebob), Place(written[1], Character.Patrick));
    }

    private static Dictionary<string, T> Index<T>(IEnumerable<T> entries, Func<T, string> preferred, Func<T, IReadOnlyList<string>> aliases) => entries
        .SelectMany(entry => aliases(entry).Prepend(preferred(entry)).Select(name => (Name: name, Entry: entry)))
        .ToDictionary(static pair => pair.Name, static pair => pair.Entry, StringComparer.OrdinalIgnoreCase);

    private string Place(string text, Character expected)
    {
        text = text.Trim();
        if (!costumes.TryGetValue(text, out CostumeName? costume)) return text;

        if (costume.Character != expected)
            throw new FormatException($"'{costume.Preferred}' is {costume.Character}'s costume, but {expected}'s goes {(expected is Character.Spongebob ? "first" : "second")}.");

        return costume.Preferred;
    }
}
