using BowlBuster.Chains;

namespace BowlBuster.Tests.Chains;

public class StepTests
{
    [Fact]
    public void Costumes_SpongebobOnly_PrintsIt() =>
        Assert.Equal("Mermaid Man", new Costumes("Mermaid Man", null).ToString());

    [Fact]
    public void Costumes_PatrickOnly_PrintsIt() =>
        Assert.Equal("Disco Patrick", new Costumes(null, "Disco Patrick").ToString());

    [Fact]
    public void Costumes_Both_PrintsSpongebobFirst() =>
        Assert.Equal("Mermaid Man, Disco Patrick", new Costumes("Mermaid Man", "Disco Patrick").ToString());

    [Fact]
    public void Costumes_None_IsEmptyAndPrintsNothing()
    {
        Assert.True(Costumes.None.IsEmpty);
        Assert.Equal(string.Empty, Costumes.None.ToString());
        Assert.Equal(Costumes.None, new Costumes(null, null));
    }

    [Fact]
    public void Costumes_Blank_Throws()
    {
        Assert.Throws<ArgumentException>(static () => new Costumes(" ", null));
        Assert.Throws<ArgumentException>(static () => new Costumes("Mermaid Man", ""));
    }

    [Fact]
    public void LevelStep_WithCostumes_PrintsThemInParentheses() =>
        Assert.Equal("BL03 (Mermaid Man)", new LevelStep("BL03", new Costumes("Mermaid Man", null)).ToString());

    [Fact]
    public void LevelStep_WithoutCostumes_PrintsTheLevelAndHasNoCostumes()
    {
        LevelStep step = new("PT02");

        Assert.Equal("PT02", step.ToString());
        Assert.Equal(Costumes.None, step.Costumes);
    }

    [Fact]
    public void LevelStep_EmptyCostumes_IsTheSameAsNone() =>
        Assert.Equal(new LevelStep("PT02"), new LevelStep("PT02", Costumes.None));

    [Theory]
    [InlineData("")]
    [InlineData("  ")]
    public void LevelStep_BlankLevel_Throws(string level) =>
        Assert.Throws<ArgumentException>(() => new LevelStep(level));

    [Theory]
    [InlineData(null, 18, "non-SB x18")]
    [InlineData(null, 1, "non-SB x1")]
    [InlineData("Dennis", 3, "Dennis x3")]
    [InlineData("Dennis", 1, "Dennis")]
    public void FillerStep_Run_PrintsGenericCountsAlwaysAndNamedCountsAboveOne(string? level, int count, string expected) =>
        Assert.Equal(expected, new FillerStep(level, count).ToString());

    [Theory]
    [InlineData(0)]
    [InlineData(-4)]
    public void FillerStep_CountBelowOne_Throws(int count) =>
        Assert.Throws<ArgumentOutOfRangeException>(() => new FillerStep("Dennis", count));

    [Fact]
    public void FillerStep_BlankLevel_Throws() =>
        Assert.Throws<ArgumentException>(static () => new FillerStep(" ", 2));
}
