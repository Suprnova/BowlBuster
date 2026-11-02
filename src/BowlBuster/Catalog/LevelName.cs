namespace BowlBuster.Catalog;

/// <summary>
/// A level's scene, its name and the other names it is accepted under. The scene tag is always accepted.
/// </summary>
public sealed class LevelName
{
    /// <summary>
    /// Creates a level name.
    /// </summary>
    /// <param name="scene">The level's scene tag.</param>
    /// <param name="name">The name BowlBuster prints, which is also accepted, or <see langword="null"/> to print the scene tag.</param>
    /// <param name="aliases">The other names accepted for the level.</param>
    /// <exception cref="ArgumentException">The scene, the name or an alias is blank.</exception>
    public LevelName(string scene, string? name = null, params ReadOnlySpan<string> aliases)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(scene);
        if (name is not null) ArgumentException.ThrowIfNullOrWhiteSpace(name);
        foreach (string alias in aliases) ArgumentException.ThrowIfNullOrWhiteSpace(alias);

        Scene = scene.Trim();
        Name = name?.Trim();
        Aliases = [.. aliases.ToArray().Select(static alias => alias.Trim())];
    }

    /// <summary>
    /// The level's scene tag.
    /// </summary>
    public string Scene { get; }

    /// <summary>
    /// The name BowlBuster prints for the level, or <see langword="null"/> when it has none.
    /// </summary>
    public string? Name { get; }

    /// <summary>
    /// The name BowlBuster prints: <see cref="Name"/>, or else <see cref="Scene"/>.
    /// </summary>
    public string Preferred => Name ?? Scene;

    /// <summary>
    /// The other names accepted for the level.
    /// </summary>
    public IReadOnlyList<string> Aliases { get; }
}
