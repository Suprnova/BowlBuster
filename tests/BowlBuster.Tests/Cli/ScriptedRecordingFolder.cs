using BowlBuster.Tests.Recordings;
using System.Text.Json.Nodes;

namespace BowlBuster.Tests.Cli;

/// <summary>
/// A scripted game's recording written to a temporary directory, the way the harness writes one. It deletes only the
/// directory it made.
/// </summary>
internal sealed class ScriptedRecordingFolder : IDisposable
{
    private readonly DirectoryInfo directory = Directory.CreateTempSubdirectory("bowlbuster-cli-");

    public ScriptedRecordingFolder(ScriptedGame game, bool complete = true, Func<JsonObject, JsonObject>? changeEvent = null)
    {
        JsonObject manifest = JsonNode.Parse(game.ManifestText)!.AsObject();
        manifest["complete"] = complete;
        manifest["interrupted"] = complete ? null : "emulator exited";
        File.WriteAllText(ManifestFile, manifest.ToJsonString());

        IEnumerable<string> events = game.EventText.Split('\n');
        File.WriteAllLines(System.IO.Path.Combine(directory.FullName, "events.jsonl"), changeEvent is null ? events : events.Select(line => changeEvent(JsonNode.Parse(line)!.AsObject()).ToJsonString()));
    }

    public string Path => directory.FullName;

    private string ManifestFile => System.IO.Path.Combine(directory.FullName, "manifest.json");

    public static ScriptedGame TwoLoads() => new ScriptedGame(ScriptedScenes.OriginStart)
        .Run(ScriptedScenes.Origin, 3)
        .Run(ScriptedScenes.Target, 4);

    public void Dispose() => directory.Delete(recursive: true);
}
