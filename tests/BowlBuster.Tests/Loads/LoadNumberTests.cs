using BowlBuster.Loads;

namespace BowlBuster.Tests.Loads;

public class LoadNumberTests
{
    [Theory]
    [InlineData(1)]
    [InlineData(23)]
    [InlineData(int.MaxValue)]
    public void Constructor_PositiveValue_KeepsIt(int value) =>
        Assert.Equal(value, new LoadNumber(value).Value);

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    [InlineData(int.MinValue)]
    public void Constructor_BelowOne_Throws(int value) =>
        Assert.Throws<ArgumentOutOfRangeException>(() => new LoadNumber(value));

    [Theory]
    [InlineData(1, Phase.First)]
    [InlineData(2, Phase.Second)]
    [InlineData(3, Phase.Third)]
    [InlineData(4, Phase.Fourth)]
    [InlineData(5, Phase.First)]
    [InlineData(6, Phase.Second)]
    [InlineData(7, Phase.Third)]
    [InlineData(8, Phase.Fourth)]
    [InlineData(23, Phase.Third)]
    [InlineData(1000, Phase.Fourth)]
    public void Phase_Load_IsTheNumberModuloFourWithZeroAsFourth(int load, Phase expected) =>
        Assert.Equal(expected, new LoadNumber(load).Phase);

    [Theory]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(10)]
    [InlineData(23)]
    public void Phase_Counter_FollowsCounterLessOneModuloFourNotCounterModuloFour(int counter)
    {
        LoadNumber load = CounterBasis.Retail.ToLoad(counter);

        int fromCounterLessOne = (counter - 1) % 4;
        int fromCounter = counter % 4;

        Assert.Equal(fromCounterLessOne, load.Value % 4);
        Assert.NotEqual(fromCounter, load.Value % 4);
    }

    [Fact]
    public void ToString_Load_NamesTheNumber() =>
        Assert.Equal("load 23", new LoadNumber(23).ToString());
}
