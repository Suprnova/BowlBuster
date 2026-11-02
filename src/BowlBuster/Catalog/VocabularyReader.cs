using BowlBuster.Chains.Parsing;
using System.Text.RegularExpressions;
using YamlDotNet.Core;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;
using static BowlBuster.Catalog.VocabularyDocument;

namespace BowlBuster.Catalog;

/// <summary>
/// Reads and validates <c>vocabulary.yaml</c>.
/// </summary>
internal static partial class VocabularyReader
{
    private static readonly IDeserializer Deserializer = new DeserializerBuilder()
        .WithNamingConvention(CamelCaseNamingConvention.Instance)
        .WithDuplicateKeyChecking()
        .Build();

    public static Vocabulary Read(TextReader reader, string source)
    {
        VocabularyDocument document;
        try
        {
            document = Deserializer.Deserialize<VocabularyDocument?>(reader) ?? new();
        }
        catch (YamlException exception)
        {
            throw new CatalogException(source, [$"Line {exception.Start.Line}, column {exception.Start.Column}: {(exception.InnerException ?? exception).Message}"]);
        }

        List<string> problems = [];
        List<LevelName> levels = [.. (document.Levels ?? []).Select(pair => ReadLevel(pair.Key, pair.Value, problems)).OfType<LevelName>()];
        List<CostumeName> costumes = [.. (document.Costumes ?? []).Select(pair => ReadCostume(pair.Key, pair.Value, problems)).OfType<CostumeName>()];
        List<WorldName> worlds = [.. (document.Worlds ?? []).OrderBy(static pair => pair.Key).Select(pair => ReadWorld(pair.Key, pair.Value, problems)).OfType<WorldName>()];
        ReportDuplicates("worlds", worlds.Select(static world => world.Name), problems);
        ReportDuplicates("task slots", worlds.SelectMany(static world => world.Tasks).Select(static task => task.Name), problems);

        Vocabulary? vocabulary = null;
        try
        {
            vocabulary = new Vocabulary(levels, costumes, worlds);
        }
        catch (ArgumentException exception)
        {
            problems.Add(exception.Message);
        }

        return problems.Count is 0 ? vocabulary! : throw new CatalogException(source, problems);
    }

    private static LevelName? ReadLevel(string scene, LevelEntry? entry, List<string> problems)
    {
        entry ??= new();
        string where = $"Level '{scene}'";
        int before = problems.Count;

        if (!SceneTag().IsMatch(scene)) problems.Add($"{where}: a scene tag is four upper-case letters or digits.");
        if (entry.Name is not null) CheckName(where, "name", entry.Name, problems);
        CheckAliases(where, entry.Aliases, problems);

        return problems.Count == before ? new LevelName(scene, entry.Name, [.. entry.Aliases ?? []]) : null;
    }

    private static CostumeName? ReadCostume(string name, CostumeEntry? entry, List<string> problems)
    {
        entry ??= new();
        string where = $"Costume '{name}'";
        int before = problems.Count;

        CheckName(where, "name", name, problems);
        CheckAliases(where, entry.Aliases, problems);
        Character? character = Enum.GetValues<Character>().Select(static value => (Character?)value).FirstOrDefault(value => string.Equals(value.ToString(), entry.Character, StringComparison.OrdinalIgnoreCase));
        if (character is null)
            problems.Add($"{where}: the character must be spongebob or patrick.");

        return problems.Count == before ? new CostumeName(name, character!.Value, [.. entry.Aliases ?? []]) : null;
    }

    private static WorldName? ReadWorld(int number, WorldEntry? entry, List<string> problems)
    {
        entry ??= new();
        string where = $"World {number}";
        int before = problems.Count;

        if (number < 1) problems.Add($"{where}: a world's number is 1 or more.");
        CheckTexts(where, entry.Name, entry.Game, problems);
        List<TaskName> tasks = [.. (entry.Tasks ?? []).OrderBy(static pair => pair.Key).Select(pair => ReadTask(number, pair.Key, pair.Value, problems)).OfType<TaskName>()];

        return problems.Count == before ? new WorldName(number, entry.Name?.Trim(), entry.Game?.Trim(), tasks) : null;
    }

    private static TaskName? ReadTask(int world, int slot, TaskEntry? entry, List<string> problems)
    {
        entry ??= new();
        string where = $"Task {world}-{slot}";
        int before = problems.Count;

        if (slot < 1) problems.Add($"{where}: a slot's number is 1 or more.");
        CheckTexts(where, entry.Name, entry.Game, problems);

        return problems.Count == before ? new TaskName(world, slot, entry.Name?.Trim(), entry.Game?.Trim()) : null;
    }

    private static void CheckTexts(string where, string? name, string? game, List<string> problems)
    {
        if (name is null && game is null) problems.Add($"{where}: needs a name or a game text.");
        if (name is not null && string.IsNullOrWhiteSpace(name)) problems.Add($"{where}: the name is blank.");
        if (game is not null && string.IsNullOrWhiteSpace(game)) problems.Add($"{where}: the game text is blank.");
    }

    private static void CheckAliases(string where, List<string>? aliases, List<string> problems)
    {
        foreach (string? alias in aliases ?? [])
            CheckName(where, "alias", alias, problems);
    }

    private static void CheckName(string where, string what, string? text, List<string> problems)
    {
        if (string.IsNullOrWhiteSpace(text)) problems.Add($"{where}: a {what} is blank.");
        else if (!ChainParser.CanName(text)) problems.Add($"{where}: the {what} '{text}' can't be written in a chain.");
    }

    private static void ReportDuplicates(string what, IEnumerable<string?> names, List<string> problems) => problems.AddRange(names
        .OfType<string>()
        .GroupBy(static name => name, StringComparer.OrdinalIgnoreCase)
        .Where(static group => group.Count() > 1)
        .Select(group => $"More than one of the {what} is named '{group.Key}'."));

    [GeneratedRegex("^[A-Z0-9]{4}$")]
    private static partial Regex SceneTag();
}
