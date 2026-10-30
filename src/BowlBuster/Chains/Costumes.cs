namespace BowlBuster.Chains;

/// <summary>
/// The costumes worn in a level, SpongeBob's and Patrick's. A level loads both characters, so both can matter; a costume
/// that doesn't matter is left out. When neither matters the costumes are <see cref="None"/>.
/// </summary>
public sealed record Costumes
{
    /// <summary>
    /// Creates the costumes worn in a level.
    /// </summary>
    /// <param name="spongebob">SpongeBob's costume, or <see langword="null"/> when it doesn't matter.</param>
    /// <param name="patrick">Patrick's costume, or <see langword="null"/> when it doesn't matter.</param>
    /// <exception cref="ArgumentException">A costume is blank.</exception>
    public Costumes(string? spongebob, string? patrick)
    {
        if (spongebob is not null) ArgumentException.ThrowIfNullOrWhiteSpace(spongebob);
        if (patrick is not null) ArgumentException.ThrowIfNullOrWhiteSpace(patrick);

        Spongebob = spongebob;
        Patrick = patrick;
    }

    /// <summary>
    /// The costumes of a level where none matter.
    /// </summary>
    public static Costumes None { get; } = new(null, null);

    /// <summary>
    /// SpongeBob's costume, if it matters.
    /// </summary>
    public string? Spongebob { get; }

    /// <summary>
    /// Patrick's costume, if it matters.
    /// </summary>
    public string? Patrick { get; }

    /// <summary>
    /// Whether no costume matters.
    /// </summary>
    public bool IsEmpty => Spongebob is null && Patrick is null;

    /// <summary>
    /// Prints the costumes with SpongeBob's first, as "Mermaid Man" or "Mermaid Man, Disco Patrick".
    /// </summary>
    /// <returns>The costumes, comma-separated, or an empty string for <see cref="None"/>.</returns>
    public override string ToString() => string.Join(", ", new[] { Spongebob, Patrick }.OfType<string>());
}
