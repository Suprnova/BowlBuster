using BowlBuster.Cli;

namespace BowlBuster.Tests;

public class VersionBannerTests
{
    [Fact]
    public void For_ReturnsAssemblyNameAndVersion()
    {
        System.Reflection.Assembly assembly = typeof(VersionBanner).Assembly;
        string expected = $"BowlBuster.Cli {assembly.GetName().Version}";

        Assert.Equal(expected, VersionBanner.For(assembly));
    }
}
