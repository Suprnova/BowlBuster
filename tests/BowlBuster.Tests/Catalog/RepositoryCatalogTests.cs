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

    [Theory]
    [InlineData("PLSB", "Mermaid Man")]
    [InlineData("PLSD", "Plain Sponge")]
    [InlineData("PLP1", "Plain Patrick")]
    [InlineData("PLPB", "Disco Patrick")]
    [InlineData("PLPA", "Caveman Patrick")]
    [InlineData("PLPC", "Goofy Goober")]
    [InlineData("PLSA", "Caveman Sponge")]
    [InlineData("PLSC", "Ripped Pants")]
    public void ResolveArchive_RepositoryCatalog_NamesTheCostumeOfEveryKnownArchive(string archive, string expected)
    {
        Vocabulary vocabulary = Vocabulary.Load(Path.Combine(AppContext.BaseDirectory, "catalog"));

        Assert.Equal(expected, vocabulary.ResolveArchive(archive));
    }

    [Theory]
    [InlineData("PLS1")]
    [InlineData("ZZZ9")]
    public void ResolveArchive_RepositoryCatalog_KeepsAnArchiveNoCostumeClaims(string archive)
    {
        Vocabulary vocabulary = Vocabulary.Load(Path.Combine(AppContext.BaseDirectory, "catalog"));

        Assert.Equal(archive, vocabulary.ResolveArchive(archive));
    }
}
