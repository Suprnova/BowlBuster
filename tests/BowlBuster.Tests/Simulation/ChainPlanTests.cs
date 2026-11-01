using BowlBuster.Chains;
using BowlBuster.Loads;
using BowlBuster.Recordings;
using BowlBuster.Simulation;

namespace BowlBuster.Tests.Simulation;

public class ChainPlanTests
{
    private static string Same(string level) => level;

    [Fact]
    public void From_FullChain_StartsAtTheOriginWithOneKeyPerLoad()
    {
        ChainPlan plan = ChainPlan.From(Chain.Parse("[load] > burn x1 > ORIG > FILL x2 > TARG"), Same);

        Assert.Equal(new LoadNumber(3), plan.FirstLoad);
        Assert.Equal(["ORIG", "FILL", "FILL", "TARG"], plan.Loads.Select(static key => key.Scene));
    }

    [Fact]
    public void From_Costumes_StayOnTheOriginAndTargetOnly()
    {
        ChainPlan plan = ChainPlan.From(Chain.Parse("[load] > ORIG (Mermaid Man) > FILL > TARG (Disco Patrick)"), Same);

        Assert.Equal(
            [new Costumes("Mermaid Man", null), Costumes.None, new Costumes(null, "Disco Patrick")],
            plan.Loads.Select(static key => key.Costumes));
    }

    [Fact]
    public void From_SceneOf_MapsEveryLevel()
    {
        ChainPlan plan = ChainPlan.From(Chain.Parse("[load] > Origin Level > Filler Level > Target Level"), static level => level[..1]);

        Assert.Equal(["O", "F", "T"], plan.Loads.Select(static key => key.Scene));
    }

    [Fact]
    public void From_Shape_TakesTheOriginLoadGiven()
    {
        ChainPlan plan = ChainPlan.From(Chain.Parse("ORIG > TARG"), Same, new LoadNumber(7));

        Assert.Equal(new LoadNumber(7), plan.FirstLoad);
    }

    [Fact]
    public void From_ShapeWithNoOriginLoad_Throws() =>
        Assert.Throws<ArgumentException>(() => ChainPlan.From(Chain.Parse("ORIG > TARG"), Same));

    [Fact]
    public void From_UnnamedFiller_Throws()
    {
        ArgumentException exception = Assert.Throws<ArgumentException>(() => ChainPlan.From(Chain.Parse("[load] > ORIG > non-SB x3 > TARG"), Same));

        Assert.Contains("non-SB x3", exception.Message, StringComparison.Ordinal);
    }
}
