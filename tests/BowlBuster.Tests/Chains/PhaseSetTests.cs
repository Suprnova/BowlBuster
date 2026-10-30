using BowlBuster.Chains;

namespace BowlBuster.Tests.Chains;

public class PhaseSetTests
{
    [Theory]
    [InlineData(Phase.First, "1st")]
    [InlineData(Phase.Second, "2nd")]
    [InlineData(Phase.Third, "3rd")]
    [InlineData(Phase.Fourth, "4th")]
    public void Ordinal_Phase_NamesItAsRunnersDo(Phase phase, string expected) =>
        Assert.Equal(expected, PhaseSet.Ordinal(phase));

    [Fact]
    public void Contains_PhasesGivenToTheConstructor_IsTrueOnlyForThose()
    {
        var set = new PhaseSet(Phase.Fourth, Phase.First);

        Assert.True(set.Contains(Phase.First));
        Assert.False(set.Contains(Phase.Second));
        Assert.False(set.Contains(Phase.Third));
        Assert.True(set.Contains(Phase.Fourth));
    }

    [Fact]
    public void Constructor_RepeatedPhase_IsTheSameSetAsOnce() =>
        Assert.Equal(new PhaseSet(Phase.Third), new PhaseSet(Phase.Third, Phase.Third));

    [Fact]
    public void All_Always_ContainsEveryPhaseInOrder() =>
        Assert.Equal([Phase.First, Phase.Second, Phase.Third, Phase.Fourth], PhaseSet.All.Phases);

    [Fact]
    public void ToString_Empty_IsNone() =>
        Assert.Equal("none", default(PhaseSet).ToString());

    [Fact]
    public void ToString_OnePhase_IsItsOrdinal() =>
        Assert.Equal("4th", new PhaseSet(Phase.Fourth).ToString());

    [Fact]
    public void ToString_TwoPhasesGivenOutOfOrder_PrintsThemInOrderJoinedByOr() =>
        Assert.Equal("1st or 4th", new PhaseSet(Phase.Fourth, Phase.First).ToString());

    [Fact]
    public void ToString_ThreePhases_PrintsCommasThenOr() =>
        Assert.Equal("1st, 2nd or 3rd", new PhaseSet(Phase.Third, Phase.First, Phase.Second).ToString());

    [Fact]
    public void ToString_AllPhases_PrintsCommasThenOr() =>
        Assert.Equal("1st, 2nd, 3rd or 4th", PhaseSet.All.ToString());

    [Theory]
    [InlineData("4th", new[] { Phase.Fourth })]
    [InlineData("4th or 1st", new[] { Phase.First, Phase.Fourth })]
    [InlineData("1st, 2nd or 3rd", new[] { Phase.First, Phase.Second, Phase.Third })]
    [InlineData("3RD OR 2ND", new[] { Phase.Second, Phase.Third })]
    [InlineData("  2nd ,3rd  ", new[] { Phase.Second, Phase.Third })]
    [InlineData("1st, 2nd, 3rd or 4th", new[] { Phase.First, Phase.Second, Phase.Third, Phase.Fourth })]
    [InlineData("1st, 2nd, or 3rd", new[] { Phase.First, Phase.Second, Phase.Third })]
    [InlineData("4th and 1st", new[] { Phase.First, Phase.Fourth })]
    [InlineData("1st, 2nd, and 3rd", new[] { Phase.First, Phase.Second, Phase.Third })]
    [InlineData("2nd AND 3rd", new[] { Phase.Second, Phase.Third })]
    [InlineData("1st 2nd", new[] { Phase.First, Phase.Second })]
    [InlineData("1,2,3", new[] { Phase.First, Phase.Second, Phase.Third })]
    [InlineData("4 1", new[] { Phase.First, Phase.Fourth })]
    public void Parse_TextWithPhaseDigits_ReturnsThosePhasesWhateverTheWording(string text, Phase[] expected) =>
        Assert.Equal(expected, PhaseSet.Parse(text).Phases);

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("5th")]
    [InlineData("first")]
    [InlineData("0th")]
    [InlineData("1st or 7th")]
    [InlineData("none")]
    [InlineData("11th")]
    [InlineData("1st or 12")]
    [InlineData("21st")]
    [InlineData("1st, 2nd or 33")]
    public void Parse_NoDigitsADigitOutsideOneToFourOrAMultiDigitNumber_Throws(string text) =>
        Assert.Throws<FormatException>(() => PhaseSet.Parse(text));

    [Fact]
    public void TryParse_Null_ReturnsFalse() =>
        Assert.False(PhaseSet.TryParse(null, out _));

    [Theory]
    [InlineData("4th")]
    [InlineData("1st or 4th")]
    [InlineData("1st, 2nd or 3rd")]
    public void Parse_PrintedSet_RoundTrips(string text) =>
        Assert.Equal(text, PhaseSet.Parse(text).ToString());
}
