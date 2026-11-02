using BowlBuster.Chains;

namespace BowlBuster.Catalog;

/// <summary>
/// The names a chain may be written in, and the preferred name each resolves to. Every name is accepted without regard
/// to case or surrounding spaces; a chain only ever holds and prints the preferred names.
/// </summary>
/// <remarks>
/// A name with no entry is kept as written. A level then prints as it was written, and a costume can only be placed by
/// its position when both costumes are written.
/// </remarks>
public sealed class Vocabulary
{
    private const string FileName = "vocabulary.yaml";

    private readonly Dictionary<string, LevelName> levels;
    private readonly Dictionary<string, CostumeName> costumes;
    private readonly Dictionary<string, CostumeName> archives;

    /// <summary>
    /// Creates a vocabulary.
    /// </summary>
    /// <param name="levels">The levels with their names.</param>
    /// <param name="costumes">The costumes with their names.</param>
    /// <param name="worlds">The pause menu's worlds with their task slots.</param>
    /// <exception cref="ArgumentException">
    /// A name is used by more than one level or by more than one costume, a scene is used by more than one level, a
    /// level's name is another level's scene, or an archive is the archive of more than one costume.
    /// </exception>
    public Vocabulary(IEnumerable<LevelName> levels, IEnumerable<CostumeName> costumes, IEnumerable<WorldName>? worlds = null)
    {
        ArgumentNullException.ThrowIfNull(levels);
        ArgumentNullException.ThrowIfNull(costumes);

        this.levels = Index("level", levels, static level => [level.Scene, .. level.Name is null ? (string[])[] : [level.Name], .. level.Aliases]);
        CostumeName[] named = [.. costumes];
        this.costumes = Index("costume", named, static costume => [costume.Preferred, .. costume.Aliases]);
        archives = Index("costume archive", named.Where(static costume => costume.Archive is not null), static costume => [costume.Archive!]);
        Worlds = [.. worlds ?? []];
    }

    /// <summary>
    /// The pause menu's worlds with their task slots.
    /// </summary>
    public IReadOnlyList<WorldName> Worlds { get; }

    /// <summary>
    /// Reads a vocabulary from the text of <c>vocabulary.yaml</c>.
    /// </summary>
    /// <param name="reader">The YAML to read.</param>
    /// <param name="source">What the YAML comes from, named by the exception when it has problems.</param>
    /// <returns>The vocabulary.</returns>
    /// <exception cref="CatalogException">The YAML is invalid or breaks the catalog's rules.</exception>
    public static Vocabulary Read(TextReader reader, string source = FileName)
    {
        ArgumentNullException.ThrowIfNull(reader);
        return VocabularyReader.Read(reader, source);
    }

    /// <summary>
    /// Reads the vocabulary from <c>vocabulary.yaml</c> in a catalog.
    /// </summary>
    /// <param name="catalogDirectory">The catalog's directory.</param>
    /// <returns>The vocabulary.</returns>
    /// <exception cref="FileNotFoundException">The catalog has no <c>vocabulary.yaml</c>.</exception>
    /// <exception cref="CatalogException">The file is invalid or breaks the catalog's rules.</exception>
    public static Vocabulary Load(string catalogDirectory)
    {
        string path = Path.Combine(catalogDirectory, FileName);
        using StreamReader reader = File.OpenText(path);
        return Read(reader, path);
    }

    /// <summary>
    /// A vocabulary with no names: every level is kept as written, and costumes can only be placed by position.
    /// </summary>
    public static Vocabulary Empty { get; } = new([], []);

    /// <summary>
    /// Resolves the tag of a player archive, as a recording names it, to the preferred name of the costume that loads it.
    /// </summary>
    /// <param name="archive">The archive's tag.</param>
    /// <returns>The costume's preferred name, or <paramref name="archive"/> when no costume has that archive.</returns>
    public string ResolveArchive(string archive)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(archive);
        return archives.TryGetValue(archive.Trim(), out CostumeName? costume) ? costume.Preferred : archive.Trim();
    }

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
    /// Resolves a level to its scene.
    /// </summary>
    /// <param name="level">The level as written: a scene tag, a name or an alias.</param>
    /// <returns>The level's scene, or <paramref name="level"/> trimmed when the level has no entry and is taken to be a scene tag.</returns>
    public string SceneOf(string level)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(level);
        return levels.TryGetValue(level.Trim(), out LevelName? entry) ? entry.Scene : level.Trim();
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

    private static Dictionary<string, T> Index<T>(string kind, IEnumerable<T> entries, Func<T, string[]> names)
    {
        List<(string Name, T Entry)> pairs = [.. entries.SelectMany(entry => names(entry).Distinct(StringComparer.OrdinalIgnoreCase).Select(name => (Name: name, Entry: entry)))];
        string[] duplicates = [.. pairs.GroupBy(static pair => pair.Name, StringComparer.OrdinalIgnoreCase).Where(static group => group.Count() > 1).Select(static group => $"'{group.Key}'")];

        return duplicates.Length is 0
            ? pairs.ToDictionary(static pair => pair.Name, static pair => pair.Entry, StringComparer.OrdinalIgnoreCase)
            : throw new ArgumentException($"More than one {kind} is named {string.Join(", ", duplicates)}.");
    }

    private string Place(string text, Character expected)
    {
        text = text.Trim();
        if (!costumes.TryGetValue(text, out CostumeName? costume)) return text;

        if (costume.Character != expected)
            throw new FormatException($"'{costume.Preferred}' is {costume.Character}'s costume, but {expected}'s goes {(expected is Character.Spongebob ? "first" : "second")}.");

        return costume.Preferred;
    }
}
