using BowlBuster.Catalog;
using BowlBuster.Chains;

namespace BowlBuster.Tests.Catalog;

public class VocabularyReadingTests
{
    private const string Full = """
        costumes:
          Mermaid Man: { character: spongebob, aliases: [MM] }
          Disco Patrick: { character: Patrick, aliases: [DP] }

        levels:
          BL03: { name: SCDA Spongeball, aliases: [SCDA SB, SCDA ball] }
          TT02: { name: Weenie }
          MNUC: {}

        worlds:
          11:
            name: SCDA
            game: Shell City, Dead Ahead
          7:
            name: Weenie
            game: No Weenie Parking Anytime
            tasks:
              2: { name: Time, game: Time Challenge }
              1: { game: "Now, How Do We Get Out Of Here ?" }
        """;

    private static Vocabulary Read(string yaml) => Vocabulary.Read(new StringReader(yaml));

    private static CatalogException ReadFailing(string yaml) => Assert.Throws<CatalogException>(() => Read(yaml));

    [Fact]
    public void Read_EveryFileSection_ReadsWorldsAndSlotsInNumberOrder()
    {
        Vocabulary vocabulary = Read(Full);

        Assert.Equal([7, 11], vocabulary.Worlds.Select(static world => world.Number));
        Assert.Equal(
            [new TaskName(7, 1, null, "Now, How Do We Get Out Of Here ?"), new TaskName(7, 2, "Time", "Time Challenge")],
            vocabulary.Worlds[0].Tasks);
        Assert.Equal(("SCDA", "Shell City, Dead Ahead"), (vocabulary.Worlds[1].Name, vocabulary.Worlds[1].GameName));
        Assert.Empty(vocabulary.Worlds[1].Tasks);
    }

    [Fact]
    public void Read_EveryFileSection_ResolvesLevelsAndCostumes()
    {
        Vocabulary vocabulary = Read(Full);

        Assert.Equal("BL03", vocabulary.SceneOf("scda sb"));
        Assert.Equal("SCDA Spongeball", vocabulary.ResolveLevel("BL03"));
        Assert.Equal("MNUC", vocabulary.ResolveLevel("mnuc"));
        Assert.Equal(new Costumes("Mermaid Man", "Disco Patrick"), vocabulary.ResolveCostumes(["mm", "DP"]));
    }

    [Fact]
    public void LabelOf_NamedTask_FollowsTheWorldsLabel()
    {
        WorldName world = Read(Full).Worlds[0];

        Assert.Equal("Weenie", world.Label);
        Assert.Equal("Weenie Time", world.LabelOf(world.Tasks[1]));
    }

    [Fact]
    public void LabelOf_TaskWithTheWorldsName_IsNotPrefixed()
    {
        WorldName world = Read("worlds:\n  8: { name: Frogfish, tasks: { 1: { name: frogfish } } }").Worlds[0];

        Assert.Equal("frogfish", world.LabelOf(world.Tasks[0]));
    }

    [Fact]
    public void LabelOf_TaskWithoutAName_IsItsGameName()
    {
        WorldName world = Read(Full).Worlds[0];

        Assert.Equal("Now, How Do We Get Out Of Here ?", world.LabelOf(world.Tasks[0]));
    }

    [Theory]
    [InlineData("")]
    [InlineData("# only a comment")]
    public void Read_NoSections_ReadsAnEmptyVocabulary(string yaml)
    {
        Vocabulary vocabulary = Read(yaml);

        Assert.Empty(vocabulary.Worlds);
        Assert.Equal("TR01", vocabulary.SceneOf("TR01"));
    }

    [Fact]
    public void Read_SomeSections_LeavesTheRestEmpty()
    {
        Vocabulary vocabulary = Read("levels:\n  TR01: { name: Rock Slide }");

        Assert.Empty(vocabulary.Worlds);
        Assert.Equal("TR01", vocabulary.SceneOf("rock slide"));
    }

    [Theory]
    [InlineData("levels:\n  tr01: { name: Rock Slide }", "tr01")]
    [InlineData("levels:\n  TR1: {}", "TR1")]
    [InlineData("levels:\n  TR01: { name: ' ' }", "blank")]
    [InlineData("levels:\n  TR01: { aliases: [''] }", "blank")]
    [InlineData("costumes:\n  Mermaid Man: { character: spongebob, aliases: [' '] }", "blank")]
    [InlineData("worlds:\n  0: { name: Weenie }", "number")]
    [InlineData("worlds:\n  -1: { name: Weenie }", "number")]
    [InlineData("worlds:\n  7: {}", "needs a name or a game text")]
    [InlineData("worlds:\n  7: { name: ' ' }", "blank")]
    [InlineData("worlds:\n  7: { name: Weenie, tasks: { 0: { name: Time } } }", "number")]
    [InlineData("worlds:\n  7: { name: Weenie, tasks: { 1: {} } }", "needs a name or a game text")]
    [InlineData("worlds:\n  7: { name: Weenie, tasks: { 1: { game: ' ' } } }", "blank")]
    [InlineData("costumes:\n  Mermaid Man: { character: squidward }", "spongebob or patrick")]
    [InlineData("costumes:\n  Mermaid Man: { aliases: [MM] }", "spongebob or patrick")]
    [InlineData("costumes:\n  Mermaid Man: { character: '1' }", "spongebob or patrick")]
    public void Read_BreakingARule_Throws(string yaml, string problem)
    {
        CatalogException exception = ReadFailing(yaml);

        Assert.Contains(problem, Assert.Single(exception.Problems), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("levels:\n  TR01: { name: Rock Slide, aliases: [RS] }\n  TT02: { name: Weenie, aliases: [rs] }")]
    [InlineData("levels:\n  TR01: { name: Rock Slide }\n  TT02: { name: tr01 }")]
    [InlineData("levels:\n  TR01: { name: Rock Slide }\n  TT02: { name: ROCK SLIDE }")]
    [InlineData("levels:\n  BL03: { name: SCDA Spongeball }\n  TT02: { name: SCDA SpongeBall }")]
    [InlineData("costumes:\n  Mermaid Man: { character: spongebob, aliases: [MM] }\n  Mighty Mouse: { character: spongebob, aliases: [mm] }")]
    [InlineData("worlds:\n  7: { name: Weenie }\n  8: { name: weenie }")]
    [InlineData("worlds:\n  7: { name: Weenie, tasks: { 1: { name: Time }, 2: { name: time } } }")]
    public void Read_DuplicateNames_Throws(string yaml) => ReadFailing(yaml);

    [Fact]
    public void Read_RepeatedTaskNamesAndInGameTextsInDifferentWorlds_IsAllowed() => Read("""
        worlds:
          7: { name: Weenie, tasks: { 2: { name: Time, game: Time Challenge } } }
          8: { name: Frogfish, tasks: { 2: { name: Time, game: Time Challenge } } }
        """);

    [Theory]
    [InlineData("Rock > Slide")]
    [InlineData("Rock, Slide")]
    [InlineData("Rock (Slide)")]
    [InlineData("Rock [Slide]")]
    [InlineData("Rock x2")]
    [InlineData("burn")]
    [InlineData("Burn Notice")]
    [InlineData("non-SB")]
    public void Read_NameTheChainNotationCannotHold_Throws(string name)
    {
        ReadFailing($"levels:\n  TR01: {{ name: \"{name}\" }}");
        ReadFailing($"levels:\n  TR01: {{ aliases: [\"{name}\"] }}");
        ReadFailing($"costumes:\n  \"{name}\": {{ character: patrick }}");
    }

    [Fact]
    public void Read_WorldsAndSlotsMayShareNamesWithLevels() => Read("""
        levels:
          TT02: { name: Weenie }
        worlds:
          7: { name: Weenie, tasks: { 1: { name: Weenie } } }
        """);

    [Fact]
    public void Read_TwoProblems_ListsBoth()
    {
        CatalogException exception = ReadFailing("levels:\n  tr01: {}\nworlds:\n  0: { name: Weenie }");

        Assert.Equal(2, exception.Problems.Count);
        Assert.Contains("tr01", exception.Problems[0], StringComparison.Ordinal);
        Assert.Contains("number", exception.Problems[1], StringComparison.Ordinal);
        Assert.All(exception.Problems, problem => Assert.Contains(problem, exception.Message, StringComparison.Ordinal));
    }

    [Fact]
    public void Read_DuplicateAndShapeProblems_ListsBoth()
    {
        CatalogException exception = ReadFailing("levels:\n  TR01: { name: Rock Slide }\n  TT02: { name: Rock Slide }\n  tt03: {}");

        Assert.Equal(2, exception.Problems.Count);
    }

    [Fact]
    public void Read_SyntaxError_ThrowsWithTheLine()
    {
        CatalogException exception = ReadFailing("levels:\n  TR01: { name: Rock Slide\n");

        Assert.Contains("Line 3,", Assert.Single(exception.Problems), StringComparison.Ordinal);
    }

    [Fact]
    public void Read_UnknownKey_ThrowsWithTheLine()
    {
        CatalogException exception = ReadFailing("levels:\n  TR01: { nme: Rock Slide }\n");

        Assert.Contains("Line 2,", Assert.Single(exception.Problems), StringComparison.Ordinal);
    }

    [Fact]
    public void Read_WorldNumberThatIsNotANumber_ThrowsWithTheLine()
    {
        CatalogException exception = ReadFailing("worlds:\n  seven: { name: Weenie }\n");

        Assert.Contains("Line 2,", Assert.Single(exception.Problems), StringComparison.Ordinal);
    }

    [Fact]
    public void Read_KeyWrittenTwice_Throws() =>
        ReadFailing("levels:\n  TR01: { name: Rock Slide }\n  TR01: { name: Rock Slide 2 }\n");

    [Fact]
    public void Read_Problems_NameTheSource()
    {
        CatalogException exception = Assert.Throws<CatalogException>(() => Vocabulary.Read(new StringReader("levels:\n  tr01: {}"), "catalog.yaml"));

        Assert.Equal("catalog.yaml", exception.File);
        Assert.StartsWith("catalog.yaml", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Load_ReadsVocabularyYamlFromTheDirectory()
    {
        using TempDirectory directory = new();
        File.WriteAllText(Path.Combine(directory.Path, "vocabulary.yaml"), Full);

        Vocabulary vocabulary = Vocabulary.Load(directory.Path);

        Assert.Equal("BL03", vocabulary.SceneOf("SCDA SB"));
    }

    [Fact]
    public void Load_InvalidFile_NamesThePath()
    {
        using TempDirectory directory = new();
        string path = Path.Combine(directory.Path, "vocabulary.yaml");
        File.WriteAllText(path, "levels:\n  tr01: {}");

        CatalogException exception = Assert.Throws<CatalogException>(() => Vocabulary.Load(directory.Path));

        Assert.Equal(path, exception.File);
    }

    [Fact]
    public void Load_NoVocabularyFile_Throws()
    {
        using TempDirectory directory = new();

        Assert.Throws<FileNotFoundException>(() => Vocabulary.Load(directory.Path));
    }

    private sealed class TempDirectory : IDisposable
    {
        public string Path { get; } = Directory.CreateTempSubdirectory().FullName;

        public void Dispose() => Directory.Delete(Path, recursive: true);
    }
}
