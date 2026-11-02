using BowlBuster.Catalog;
using System.Text.Json;

namespace BowlBuster.Recordings;

/// <summary>
/// Reads a recording the harness wrote to a directory.
/// </summary>
/// <remarks>
/// A recording's directory holds <c>manifest.json</c>, <c>events.jsonl</c> and, when captures were asked for, a
/// <c>captures</c> directory that <see cref="FileCaptureSource"/> reads.
/// </remarks>
public static class RecordingDirectory
{
    internal const string ManifestFile = "manifest.json";

    private const string EventsFile = "events.jsonl";

    /// <summary>
    /// Reads a recording from its directory.
    /// </summary>
    /// <param name="path">The recording's directory.</param>
    /// <param name="vocabulary">Names the player archives each load wore.</param>
    /// <returns>The recording.</returns>
    /// <exception cref="DirectoryNotFoundException">There is no such directory.</exception>
    /// <exception cref="FileNotFoundException">The directory lacks <c>manifest.json</c> or <c>events.jsonl</c>.</exception>
    /// <exception cref="FormatException">
    /// The recording is incomplete, which its manifest says: it was still being written or was cut short. Or a file is
    /// not valid, as <see cref="RecordingReader.Read"/> reports.
    /// </exception>
    public static Recording Read(string path, Vocabulary vocabulary)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        ArgumentNullException.ThrowIfNull(vocabulary);

        if (!Directory.Exists(path)) throw new DirectoryNotFoundException($"The recording directory '{path}' does not exist.");

        string manifest = File.ReadAllText(Path.Combine(path, ManifestFile));
        RequireComplete(path, manifest);

        using StreamReader events = File.OpenText(Path.Combine(path, EventsFile));
        return RecordingReader.Read(new StringReader(manifest), events, vocabulary);
    }

    private static void RequireComplete(string path, string manifest)
    {
        try
        {
            using JsonDocument document = JsonDocument.Parse(manifest);
            JsonElement root = document.RootElement;
            if (root.ValueKind is JsonValueKind.Object && root.TryGetProperty("complete", out JsonElement complete) && complete.ValueKind is JsonValueKind.True) return;

            string reason = root.ValueKind is JsonValueKind.Object && root.TryGetProperty("interrupted", out JsonElement interrupted) && interrupted.ValueKind is JsonValueKind.String
                ? $": {interrupted.GetString()}"
                : "";
            throw new FormatException($"The recording at '{path}' is incomplete{reason}. It was still being written or was cut short.");
        }
        catch (JsonException exception)
        {
            throw new FormatException($"The manifest of the recording at '{path}' is not valid JSON: {exception.Message}", exception);
        }
    }
}
