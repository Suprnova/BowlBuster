using BowlBuster.Catalog;

namespace BowlBuster.Tests.Catalog;

public class RepositoryCatalogTests
{
    [Fact]
    public void Load_RepositoryCatalog_ReadsWithoutProblems()
    {
        Vocabulary vocabulary = Vocabulary.Load(Path.Combine(AppContext.BaseDirectory, "catalog"));

        Assert.Equal("BL03", vocabulary.SceneOf("BL03"));
        Assert.NotEqual("BL03", vocabulary.ResolveLevel("BL03"));
    }
}
