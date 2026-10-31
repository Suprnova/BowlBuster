using BowlBuster.Chains.Vocabulary;

namespace BowlBuster.Tests.Chains.Vocabulary;

/// <summary>
/// The names the tests write chains in. The library holds no game names: they come from the catalog.
/// </summary>
internal static class TestVocabulary
{
    public static IReadOnlyList<CostumeName> Costumes { get; } =
    [
        new("Plain Sponge", Character.Spongebob, "PS"),
        new("Mermaid Man", Character.Spongebob, "MM"),
        new("Ripped Pants", Character.Spongebob, "RPS"),
        new("Caveman Sponge", Character.Spongebob, "CMS"),
        new("Plain Patrick", Character.Patrick, "PP"),
        new("Disco Patrick", Character.Patrick, "DP"),
        new("Caveman Patrick", Character.Patrick, "CMP"),
        new("Goofy Goober", Character.Patrick, "GGP"),
    ];

    public static ChainVocabulary CostumesOnly { get; } = new([], Costumes);

    public static ChainVocabulary WithLevels { get; } = new(
        [
            new("Rock Slide", "TR01"),
            new("Mindy Skip", "PT02", "mindy"),
            new("Frogfish", "B101"),
            new("No Cheese", "BB02"),
        ],
        Costumes);
}
