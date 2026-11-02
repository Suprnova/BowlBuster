using BowlBuster.Catalog;
using BowlBuster.Chains;
using BowlBuster.Simulation;

namespace BowlBuster.Tests.Catalog;

public class VocabularyTests
{
    private readonly Vocabulary vocabulary = new(
        [
            new LevelName("TR01", "Rock Slide"),
            new LevelName("BL03", "SCDA Spongeball", "SCDA SB"),
            new LevelName("MNUC"),
        ],
        Vocabulary.KnownCostumes);

    [Theory]
    [InlineData("Rock Slide", "Rock Slide")]
    [InlineData("TR01", "Rock Slide")]
    [InlineData("tr01", "Rock Slide")]
    [InlineData("  ROCK SLIDE  ", "Rock Slide")]
    [InlineData("SCDA SB", "SCDA Spongeball")]
    [InlineData("bl03", "SCDA Spongeball")]
    public void ResolveLevel_KnownName_ReturnsThePreferredName(string text, string expected) =>
        Assert.Equal(expected, vocabulary.ResolveLevel(text));

    [Theory]
    [InlineData("Rub a Dub", "Rub a Dub")]
    [InlineData("  DE02 ", "DE02")]
    public void ResolveLevel_UnknownName_IsKeptAsWritten(string text, string expected) =>
        Assert.Equal(expected, vocabulary.ResolveLevel(text));

    [Fact]
    public void ResolveLevel_LevelWithoutAName_ReturnsItsScene() =>
        Assert.Equal("MNUC", vocabulary.ResolveLevel("mnuc"));

    [Theory]
    [InlineData("Rock Slide", "TR01")]
    [InlineData("TR01", "TR01")]
    [InlineData("tr01", "TR01")]
    [InlineData("  ROCK SLIDE  ", "TR01")]
    [InlineData("SCDA SB", "BL03")]
    [InlineData(" bl03 ", "BL03")]
    [InlineData("mnuc", "MNUC")]
    public void SceneOf_KnownName_ReturnsTheScene(string text, string expected) =>
        Assert.Equal(expected, vocabulary.SceneOf(text));

    [Theory]
    [InlineData("Rub a Dub", "Rub a Dub")]
    [InlineData("  DE02 ", "DE02")]
    public void SceneOf_UnknownName_IsReturnedTrimmed(string text, string expected) =>
        Assert.Equal(expected, vocabulary.SceneOf(text));

    [Fact]
    public void SceneOf_Blank_Throws() =>
        Assert.Throws<ArgumentException>(() => vocabulary.SceneOf(" "));

    [Fact]
    public void SceneOf_ChainWrittenInNames_KeysThePlanByScene()
    {
        Chain chain = Chain.Parse("[load] > rock slide > scda sb > TR01", vocabulary);

        ChainPlan plan = ChainPlan.From(chain, vocabulary.SceneOf);

        Assert.Equal(["TR01", "BL03", "TR01"], plan.Loads.Select(static key => key.Scene));
    }

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
    [InlineData("Caveman Sponge", "Caveman Sponge")]
    [InlineData("cms", "Caveman Sponge")]
    [InlineData("ripped pants", "Ripped Pants")]
    [InlineData("RPS", "Ripped Pants")]
    public void ResolveCostumes_LoneSpongebobCostume_GoesInSpongebobsSlot(string text, string expected) =>
        Assert.Equal(new Costumes(expected, null), vocabulary.ResolveCostumes([text]));

    [Theory]
    [InlineData("DP", "Disco Patrick")]
    [InlineData("pp", "Plain Patrick")]
    [InlineData("Goofy Goober", "Goofy Goober")]
    [InlineData("ggp", "Goofy Goober")]
    [InlineData("caveman patrick", "Caveman Patrick")]
    [InlineData("CMP", "Caveman Patrick")]
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
    public void ResolveCostumes_CavemanPair_PlacesEachInItsCharactersSlot() =>
        Assert.Equal(new Costumes("Caveman Sponge", "Caveman Patrick"), vocabulary.ResolveCostumes(["CMS", "CMP"]));

    [Fact]
    public void ResolveCostumes_PatricksCavemanFirst_Throws() =>
        Assert.Throws<FormatException>(() => vocabulary.ResolveCostumes(["Caveman Patrick", "DP"]));

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
        Assert.Throws<ArgumentException>(static () => new Vocabulary([new LevelName("AAAA", "A", "X"), new LevelName("BBBB", "B", "x")], []));

    [Fact]
    public void Constructor_AliasEqualToAnotherLevelsPreferredName_Throws() =>
        Assert.Throws<ArgumentException>(static () => new Vocabulary([new LevelName("AAAA", "A"), new LevelName("BBBB", "B", "a")], []));

    [Fact]
    public void Constructor_TwoLevelsWithOneScene_Throws() =>
        Assert.Throws<ArgumentException>(static () => new Vocabulary([new LevelName("AAAA", "A"), new LevelName("aaaa", "B")], []));

    [Fact]
    public void Constructor_NameEqualToAnotherLevelsScene_Throws() =>
        Assert.Throws<ArgumentException>(static () => new Vocabulary([new LevelName("AAAA"), new LevelName("BBBB", "aaaa")], []));

    [Fact]
    public void Constructor_NameEqualToItsOwnScene_IsAccepted() =>
        Assert.Equal("AAAA", new Vocabulary([new LevelName("AAAA", "AAAA")], []).SceneOf("aaaa"));

    [Fact]
    public void Constructor_AbbreviationUsedByTwoCostumes_Throws() =>
        Assert.Throws<ArgumentException>(static () => new Vocabulary([], [new CostumeName("A", Character.Spongebob, "X"), new CostumeName("B", Character.Patrick, "x")]));

    [Fact]
    public void Constructor_BlankName_Throws()
    {
        Assert.Throws<ArgumentException>(static () => new LevelName(" "));
        Assert.Throws<ArgumentException>(static () => new LevelName("AAAA", " "));
        Assert.Throws<ArgumentException>(static () => new LevelName("AAAA", "A", ""));
        Assert.Throws<ArgumentException>(static () => new CostumeName("", Character.Patrick));
    }
}
