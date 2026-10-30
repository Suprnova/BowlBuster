using BowlBuster.Chains;
using BowlBuster.Chains.Vocabulary;

namespace BowlBuster.Tests.Chains.Vocabulary;

public class ChainVocabularyTests
{
    private readonly ChainVocabulary vocabulary = new(
        [
            new LevelName("Rock Slide", "TR01"),
            new LevelName("Mindy Skip", "PT02", "mindy"),
        ],
        ChainVocabulary.KnownCostumes);

    [Theory]
    [InlineData("Rock Slide", "Rock Slide")]
    [InlineData("TR01", "Rock Slide")]
    [InlineData("tr01", "Rock Slide")]
    [InlineData("  ROCK SLIDE  ", "Rock Slide")]
    [InlineData("MINDY", "Mindy Skip")]
    [InlineData("pt02", "Mindy Skip")]
    public void ResolveLevel_KnownName_ReturnsThePreferredName(string text, string expected) =>
        Assert.Equal(expected, vocabulary.ResolveLevel(text));

    [Theory]
    [InlineData("Rub a Dub", "Rub a Dub")]
    [InlineData("  BB02 ", "BB02")]
    public void ResolveLevel_UnknownName_IsKeptAsWritten(string text, string expected) =>
        Assert.Equal(expected, vocabulary.ResolveLevel(text));

    [Theory]
    [InlineData("")]
    [InlineData("  ")]
    public void ResolveLevel_Blank_Throws(string text) =>
        Assert.Throws<ArgumentException>(() => vocabulary.ResolveLevel(text));

    [Theory]
    [InlineData("MM", "Mermaid Man")]
    [InlineData("mm", "Mermaid Man")]
    [InlineData("Mermaid Man", "Mermaid Man")]
    [InlineData(" ps ", "Plain Sponge")]
    [InlineData("Spongegar", "Spongegar")]
    [InlineData("ripped shorts", "Ripped Shorts")]
    public void ResolveCostumes_LoneSpongebobCostume_GoesInSpongebobsSlot(string text, string expected) =>
        Assert.Equal(new Costumes(expected, null), vocabulary.ResolveCostumes([text]));

    [Theory]
    [InlineData("DP", "Disco Patrick")]
    [InlineData("pp", "Plain Patrick")]
    [InlineData("Goofy Goober", "Goofy Goober")]
    [InlineData("caveman", "Caveman")]
    public void ResolveCostumes_LonePatrickCostume_GoesInPatricksSlot(string text, string expected) =>
        Assert.Equal(new Costumes(null, expected), vocabulary.ResolveCostumes([text]));

    [Fact]
    public void ResolveCostumes_PairInOrder_ResolvesBothToPreferredNames() =>
        Assert.Equal(new Costumes("Mermaid Man", "Disco Patrick"), vocabulary.ResolveCostumes(["MM", "dp"]));

    [Fact]
    public void ResolveCostumes_PairOfUnknownCostumes_IsPlacedByPosition() =>
        Assert.Equal(new Costumes("Mystery", "Enigma"), vocabulary.ResolveCostumes(["Mystery", "Enigma"]));

    [Fact]
    public void ResolveCostumes_KnownCostumeWithAnUnknownOne_PlacesTheUnknownInTheOtherSlot()
    {
        Assert.Equal(new Costumes("Mermaid Man", "Mystery"), vocabulary.ResolveCostumes(["MM", "Mystery"]));
        Assert.Equal(new Costumes("Mystery", "Disco Patrick"), vocabulary.ResolveCostumes(["Mystery", "DP"]));
    }

    [Fact]
    public void ResolveCostumes_PairWithPatricksCaveman_PlacesItInPatricksSlot() =>
        Assert.Equal(new Costumes("Spongegar", "Caveman"), vocabulary.ResolveCostumes(["spongegar", "Caveman"]));

    [Fact]
    public void ResolveCostumes_PatricksCavemanFirst_Throws() =>
        Assert.Throws<FormatException>(() => vocabulary.ResolveCostumes(["Caveman", "DP"]));

    [Fact]
    public void ResolveCostumes_PatrickFirst_Throws() =>
        Assert.Throws<FormatException>(() => vocabulary.ResolveCostumes(["DP", "MM"]));

    [Fact]
    public void ResolveCostumes_TwoCostumesOfOneCharacter_Throws()
    {
        Assert.Throws<FormatException>(() => vocabulary.ResolveCostumes(["MM", "PS"]));
        Assert.Throws<FormatException>(() => vocabulary.ResolveCostumes(["DP", "PP"]));
    }

    [Fact]
    public void ResolveCostumes_LoneUnknownCostume_Throws() =>
        Assert.Throws<FormatException>(() => vocabulary.ResolveCostumes(["Mystery"]));

    [Theory]
    [InlineData(0)]
    [InlineData(3)]
    public void ResolveCostumes_NotOneOrTwo_Throws(int count) =>
        Assert.Throws<ArgumentException>(() => vocabulary.ResolveCostumes([.. Enumerable.Repeat("MM", count)]));

    [Fact]
    public void Constructor_AliasUsedByTwoLevels_Throws() =>
        Assert.Throws<ArgumentException>(static () => new ChainVocabulary([new LevelName("A", "X"), new LevelName("B", "x")], []));

    [Fact]
    public void Constructor_AliasEqualToAnotherLevelsPreferredName_Throws() =>
        Assert.Throws<ArgumentException>(static () => new ChainVocabulary([new LevelName("A"), new LevelName("B", "a")], []));

    [Fact]
    public void Constructor_AbbreviationUsedByTwoCostumes_Throws() =>
        Assert.Throws<ArgumentException>(static () => new ChainVocabulary([], [new CostumeName("A", Character.Spongebob, "X"), new CostumeName("B", Character.Patrick, "x")]));

    [Fact]
    public void Constructor_BlankName_Throws()
    {
        Assert.Throws<ArgumentException>(static () => new LevelName(" "));
        Assert.Throws<ArgumentException>(static () => new LevelName("A", ""));
        Assert.Throws<ArgumentException>(static () => new CostumeName("", Character.Patrick));
    }
}
