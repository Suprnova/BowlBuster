using BowlBuster.Chains;
using BowlBuster.Loads;
using BowlBuster.Tests.Chains.Vocabulary;

namespace BowlBuster.Tests.Chains.Parsing;

public class ChainParsingTests
{
    [Theory]
    [InlineData("BL03 > PT02")]
    [InlineData("[load] > BL03 > PT02")]
    [InlineData("[load] > burn x1 > BL03 > PT02")]
    [InlineData("[load] > burn x3 > SCDA Spongeball > Knucklehead")]
    [InlineData("[load] > BL01 > non-SB x11 > DE02")]
    [InlineData("[load] > burn x2 > BL03 (Mermaid Man) > B101 x18 > TR01")]
    [InlineData("SCDA Spongeball (Mermaid Man) > non-SB x18 > Rock Slide [target: 1st or 4th]")]
    [InlineData("A (Mermaid Man, Disco Patrick) > Dennis x3 > Dennis > non-SB x1 > B (Disco Patrick)")]
    [InlineData("[load] > Rub a Dub > Frogfish x3 > Rock Slide")]
    public void Parse_CanonicalText_PrintsBackUnchanged(string text) =>
        Assert.Equal(text, Chain.Parse(text, TestVocabulary.CostumesOnly).ToString());

    [Fact]
    public void Parse_RockSlide_ReadsEveryPart()
    {
        Chain chain = Chain.Parse("[load] > burn x2 > BL03 (Mermaid Man) > B101 x18 > TR01", TestVocabulary.CostumesOnly);

        Assert.Equal(2, chain.Burns);
        Assert.Equal(new LevelStep("BL03", new Costumes("Mermaid Man", null)), chain.Origin);
        Assert.Equal([new FillerStep("B101", 18)], chain.Fillers);
        Assert.Equal(new LevelStep("TR01"), chain.Target);
        Assert.Equal(new ChainTiming(new LoadNumber(4), new LoadNumber(23), 19), chain.Timing);
    }

    [Fact]
    public void Parse_Shape_ReadsTargetPhases()
    {
        Chain chain = Chain.Parse("BL03 > non-SB x18 > TR01 [target: 3rd or 4th]", TestVocabulary.CostumesOnly);

        Assert.Null(chain.Burns);
        Assert.Equal(new PhaseSet(Phase.Third, Phase.Fourth), chain.TargetPhases);
        Assert.Equal([new FillerStep(null, 18)], chain.Fillers);
    }

    [Fact]
    public void Parse_AliasesAndAbbreviations_AreReplacedByPreferredNames()
    {
        Chain chain = Chain.Parse("[load] > burn x2 > bl03 (mm) > b101 x18 > tr01 (pp)", TestVocabulary.WithLevels);

        Assert.Equal("[load] > burn x2 > bl03 (Mermaid Man) > Frogfish x18 > Rock Slide (Plain Patrick)", chain.ToString());
    }

    [Fact]
    public void Parse_KeywordsInAnyCase_PrintsCanonicalKeywords()
    {
        Assert.Equal("[load] > burn x2 > A > non-SB x3 > B", Chain.Parse("[LOAD] > BURN X2 > A > NON-SB X3 > B").ToString());
        Assert.Equal("A > non-SB x3 > B [target: 4th]", Chain.Parse("A > Non-Sb x3 > B [TARGET: 4TH]").ToString());
    }

    [Fact]
    public void Parse_ExtraWhitespace_IsIgnored() =>
        Assert.Equal("[load] > burn x1 > A > B", Chain.Parse("  [ load ]>burn   x1>A  >  B  ").ToString());

    [Fact]
    public void Parse_NoVocabulary_KeepsNamesAsWritten() =>
        Assert.Equal("[load] > tr01 > b101 x2 > Rock Slide", Chain.Parse("[load] > tr01 > b101 x2 > Rock Slide").ToString());

    [Fact]
    public void Parse_FillerWithoutCount_IsOneLoad()
    {
        Chain chain = Chain.Parse("A > non-SB > Dennis > B");

        Assert.Equal([new FillerStep(null, 1), new FillerStep("Dennis", 1)], chain.Fillers);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData(">")]
    [InlineData("A")]
    [InlineData("A >")]
    [InlineData("> A > B")]
    [InlineData("A > > B")]
    [InlineData("[load]")]
    [InlineData("[load] > A")]
    [InlineData("[load] > burn x1 > A")]
    [InlineData("[load] > non-SB x3 > Knucklehead")]
    [InlineData("A > B x2")]
    [InlineData("A x2 > B")]
    [InlineData("A > non-SB x0 > B")]
    [InlineData("A > Dennis x0 > B")]
    [InlineData("burn x1 > A > B")]
    [InlineData("[load] > A > burn x1 > B")]
    [InlineData("[load] > burn x1 > burn x2 > A > B")]
    [InlineData("[load] > burn x0 > A > B")]
    [InlineData("[load] > burn BB02 x2 > A > B")]
    [InlineData("[load] > burn > A > B")]
    [InlineData("A > [load] > B")]
    [InlineData("A (Mermaid Man > B")]
    [InlineData("A > Dennis (Mermaid Man) > B")]
    [InlineData("A > non-SB (MM) x2 > B")]
    [InlineData("A () > B")]
    [InlineData("A (MM, DP, PS) > B")]
    [InlineData("A (MM,) > B")]
    [InlineData("A (Mystery) > B")]
    [InlineData("A (DP, MM) > B")]
    [InlineData("[load] > A > B [target: 4th]")]
    [InlineData("A > B [target: 5th]")]
    [InlineData("A > B [target: ]")]
    [InlineData("A > B [target: 4th")]
    [InlineData("A > non-SB x99999999999 > B")]
    public void Parse_NotAChain_ThrowsFormatException(string text) =>
        Assert.Throws<FormatException>(() => Chain.Parse(text, TestVocabulary.CostumesOnly));

    [Fact]
    public void Parse_Null_Throws() =>
        Assert.Throws<ArgumentNullException>(static () => Chain.Parse(null!));

    [Fact]
    public void TryParse_Chain_ReturnsItAndTrue()
    {
        bool parsed = Chain.TryParse("[load] > BL03 > PT02", TestVocabulary.CostumesOnly, out Chain? chain);

        Assert.True(parsed);
        Assert.Equal("[load] > BL03 > PT02", chain!.ToString());
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("A")]
    [InlineData("A (Mystery) > B")]
    public void TryParse_NotAChain_ReturnsFalseAndNull(string? text)
    {
        bool parsed = Chain.TryParse(text, TestVocabulary.CostumesOnly, out Chain? chain);

        Assert.False(parsed);
        Assert.Null(chain);
    }
}
