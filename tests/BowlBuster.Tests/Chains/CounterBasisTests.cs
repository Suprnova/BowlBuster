using BowlBuster.Chains;

namespace BowlBuster.Tests.Chains;

public class CounterBasisTests
{
    private readonly CounterBasis retail = CounterBasis.Retail;

    [Fact]
    public void Retail_Always_BootsIntoMnusAtCounterOne()
    {
        Assert.Equal("MNUS", retail.BootScene);
        Assert.Equal(1, retail.BootCounter);
    }

    [Theory]
    [InlineData(2, 1)]
    [InlineData(3, 2)]
    [InlineData(4, 3)]
    [InlineData(23, 22)]
    public void ToLoad_RetailCounter_ReturnsCounterLessOne(int counter, int expected) =>
        Assert.Equal(new LoadNumber(expected), retail.ToLoad(counter));

    [Theory]
    [InlineData(6, 1)]
    [InlineData(9, 4)]
    [InlineData(30, 25)]
    public void ToLoad_BasisBootingAtCounterFive_ReturnsCounterLessFive(int counter, int expected)
    {
        CounterBasis basis = new("MNUS", 5);

        Assert.Equal(new LoadNumber(expected), basis.ToLoad(counter));
    }

    [Theory]
    [InlineData(1)]
    [InlineData(0)]
    [InlineData(-3)]
    public void ToLoad_BootCounterOrBelow_Throws(int counter) =>
        Assert.Throws<ArgumentOutOfRangeException>(() => retail.ToLoad(counter));

    [Theory]
    [InlineData(1, 2)]
    [InlineData(4, 5)]
    [InlineData(22, 23)]
    public void ToCounter_Load_ReturnsLoadPlusBootCounter(int load, int expected) =>
        Assert.Equal(expected, retail.ToCounter(new LoadNumber(load)));

    [Theory]
    [InlineData(1, 1)]
    [InlineData(1, 7)]
    [InlineData(5, 40)]
    public void ToCounter_ThenToLoad_RoundTrips(int bootCounter, int load)
    {
        CounterBasis basis = new("BB02", bootCounter);
        LoadNumber original = new(load);

        LoadNumber roundTripped = basis.ToLoad(basis.ToCounter(original));

        Assert.Equal(original, roundTripped);
    }
}
