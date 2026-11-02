namespace BowlBuster.Catalog;

/// <summary>
/// The shape of <c>vocabulary.yaml</c> as YAML deserializes it, before it is validated.
/// </summary>
internal sealed class VocabularyDocument
{
    public Dictionary<string, CostumeEntry>? Costumes { get; set; }

    public Dictionary<string, LevelEntry>? Levels { get; set; }

    public Dictionary<int, WorldEntry>? Worlds { get; set; }

    public sealed class CostumeEntry
    {
        public string? Character { get; set; }

        public string? Archive { get; set; }

        public List<string>? Aliases { get; set; }
    }

    public sealed class LevelEntry
    {
        public string? Name { get; set; }

        public List<string>? Aliases { get; set; }
    }

    public sealed class WorldEntry
    {
        public string? Name { get; set; }

        public string? Game { get; set; }

        public Dictionary<int, TaskEntry>? Tasks { get; set; }
    }

    public sealed class TaskEntry
    {
        public string? Name { get; set; }

        public string? Game { get; set; }
    }
}
