using BowlBuster.Chains;
using BowlBuster.Loads;

namespace BowlBuster.Tests.Chains;

public class ChainTests
{
    private static Chain Full(int burns, string origin, FillerStep[] fillers, string target, Costumes? originCostumes = null) =>
        new(burns, new LevelStep(origin, originCostumes), fillers, new LevelStep(target));

    private static Chain Shape(string origin, FillerStep[] fillers, string target, PhaseSet? targetPhases = null) =>
        new(null, new LevelStep(origin), fillers, new LevelStep(target), targetPhases);

    private static Chain RockSlide() =>
        Full(2, "BL03", [new FillerStep("B101", 18)], "TR01", new Costumes("Mermaid Man", null));

    [Fact]
    public void Timing_OriginRightAfterLoad_PutsOriginOnLoadTwoAndTargetOnLoadThree()
    {
        Chain chain = Full(0, "BL03", [], "PT02");

        ChainTiming? timing = chain.Timing;

        Assert.Equal(new ChainTiming(new LoadNumber(2), new LoadNumber(3), 1), timing);
        Assert.Equal(Phase.Third, timing!.TargetPhase);
    }

    [Fact]
    public void Timing_OneBurn_MovesTheTargetToTheFourthLoad()
    {
        Chain chain = Full(1, "BL03", [], "PT02");

        ChainTiming? timing = chain.Timing;

        Assert.Equal(new LoadNumber(4), timing!.Target);
        Assert.Equal(Phase.Fourth, timing.TargetPhase);
    }

    [Fact]
    public void Timing_ThreeBurns_PutsOriginOnLoadFiveAndTargetOnLoadSix()
    {
        Chain chain = Full(3, "SCDA Spongeball", [], "Knucklehead");

        ChainTiming? timing = chain.Timing;

        Assert.Equal(new ChainTiming(new LoadNumber(5), new LoadNumber(6), 1), timing);
        Assert.Equal(Phase.Second, timing!.TargetPhase);
    }

    [Fact]
    public void Timing_ElevenGenericFillers_PutsTargetTwelveLoadsAfterTheOrigin()
    {
        Chain chain = Full(0, "BL01", [new FillerStep(null, 11)], "DE02");

        ChainTiming? timing = chain.Timing;

        Assert.Equal(new ChainTiming(new LoadNumber(2), new LoadNumber(14), 12), timing);
        Assert.Equal(Phase.Second, timing!.TargetPhase);
    }

    [Fact]
    public void Timing_RockSlide_PutsOriginOnLoadFourAndTargetOnLoadTwentyThree()
    {
        ChainTiming? timing = RockSlide().Timing;

        Assert.Equal(new ChainTiming(new LoadNumber(4), new LoadNumber(23), 19), timing);
        Assert.Equal(Phase.Third, timing!.TargetPhase);
    }

    [Fact]
    public void Timing_Shape_IsNull() =>
        Assert.Null(Shape("BL03", [], "PT02").Timing);

    [Fact]
    public void NumberLoads_RockSlide_AssignsEveryStepItsLoads()
    {
        IReadOnlyList<PlacedStep> steps = RockSlide().NumberLoads();

        Assert.Equal(
            [
                new PlacedStep("[load]", new LoadNumber(1), new LoadNumber(1)),
                new PlacedStep("burn x2", new LoadNumber(2), new LoadNumber(3)),
                new PlacedStep("BL03 (Mermaid Man)", new LoadNumber(4), new LoadNumber(4)),
                new PlacedStep("B101 x18", new LoadNumber(5), new LoadNumber(22)),
                new PlacedStep("TR01", new LoadNumber(23), new LoadNumber(23)),
            ],
            steps);
    }

    [Fact]
    public void NumberLoads_NoBurns_OmitsTheBurnStep()
    {
        IReadOnlyList<PlacedStep> steps = Full(0, "BL01", [new FillerStep(null, 11)], "DE02").NumberLoads();

        Assert.Equal(
            [
                new PlacedStep("[load]", new LoadNumber(1), new LoadNumber(1)),
                new PlacedStep("BL01", new LoadNumber(2), new LoadNumber(2)),
                new PlacedStep("non-SB x11", new LoadNumber(3), new LoadNumber(13)),
                new PlacedStep("DE02", new LoadNumber(14), new LoadNumber(14)),
            ],
            steps);
    }

    [Fact]
    public void NumberLoads_Shape_Throws() =>
        Assert.Throws<InvalidOperationException>(static () => Shape("BL03", [], "PT02").NumberLoads());

    [Theory]
    [InlineData("3rd or 4th", 19, "1st or 4th")]
    [InlineData("1st", 1, "4th")]
    [InlineData("2nd", 4, "2nd")]
    [InlineData("1st", 2, "3rd")]
    [InlineData("4th or 1st", 12, "4th or 1st")]
    [InlineData("3rd", 3, "4th")]
    public void OriginPhases_Shape_AreTheTargetPhasesKLoadsEarlier(string targetPhases, int k, string expected)
    {
        Chain chain = Shape("BL03", k > 1 ? [new FillerStep(null, k - 1)] : [], "PT02", PhaseSet.Parse(targetPhases));

        Assert.Equal(PhaseSet.Parse(expected), chain.OriginPhases);
    }

    [Fact]
    public void OriginPhases_ShapeWithoutTargetPhases_AreAllFour() =>
        Assert.Equal(PhaseSet.All, Shape("BL03", [new FillerStep(null, 4)], "PT02").OriginPhases);

    [Fact]
    public void OriginPhases_FullChain_IsThePhaseOfTheOriginsLoad()
    {
        Assert.Equal(new PhaseSet(Phase.Fourth), RockSlide().OriginPhases);
        Assert.Equal(new PhaseSet(Phase.Second), Full(0, "BL03", [], "PT02").OriginPhases);
    }

    [Fact]
    public void K_FillerRuns_IsTheirTotalLoadsPlusOne() =>
        Assert.Equal(22, Shape("A", [new FillerStep(null, 3), new FillerStep("Dennis", 18)], "B").K);

    [Fact]
    public void ToString_FullChains_PrintsLoadBurnsAndFillers()
    {
        Assert.Equal("[load] > BL03 > PT02", Full(0, "BL03", [], "PT02").ToString());
        Assert.Equal("[load] > burn x1 > BL03 > PT02", Full(1, "BL03", [], "PT02").ToString());
        Assert.Equal("[load] > BL01 > non-SB x11 > DE02", Full(0, "BL01", [new FillerStep(null, 11)], "DE02").ToString());
        Assert.Equal("[load] > burn x2 > BL03 (Mermaid Man) > B101 x18 > TR01", RockSlide().ToString());
    }

    [Fact]
    public void ToString_Shapes_PrintsTargetPhasesLast()
    {
        Assert.Equal("BL03 > PT02", Shape("BL03", [], "PT02").ToString());
        Assert.Equal(
            "SCDA Spongeball > non-SB x18 > Rock Slide [target: 1st or 4th]",
            Shape("SCDA Spongeball", [new FillerStep(null, 18)], "Rock Slide", new PhaseSet(Phase.First, Phase.Fourth)).ToString());
    }

    [Fact]
    public void ToString_Fillers_PrintsCountsOnlyWhereTheyAreNeeded()
    {
        Chain chain = Shape("A", [new FillerStep(null, 1), new FillerStep("Dennis", 1), new FillerStep("Dennis", 3)], "B");

        Assert.Equal("A > non-SB x1 > Dennis > Dennis x3 > B", chain.ToString());
    }

    [Fact]
    public void Constructor_NegativeBurns_Throws() =>
        Assert.Throws<ArgumentOutOfRangeException>(static () => Full(-1, "A", [], "B"));

    [Fact]
    public void Constructor_TargetPhasesOnAFullChain_Throws() =>
        Assert.Throws<ArgumentException>(static () => new Chain(0, new LevelStep("A"), [], new LevelStep("B"), PhaseSet.All));

    [Fact]
    public void Constructor_MissingOriginOrTarget_Throws()
    {
        Assert.Throws<ArgumentNullException>(static () => new Chain(null, null!, [], new LevelStep("B")));
        Assert.Throws<ArgumentNullException>(static () => new Chain(null, new LevelStep("A"), [], null!));
    }
}
