using BowlBuster.Catalog;

namespace BowlBuster.Tests.Catalog;

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

    public static Vocabulary CostumesOnly { get; } = new([], Costumes);

    public static Vocabulary WithLevels { get; } = new(
        [
            new("TR01", "Rock Slide"),
            new("B101", "Frogfish"),
            new("BB02", "No Cheese"),
        ],
        Costumes);
}
