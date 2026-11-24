using BowlBuster.Tests.Recordings;
using System.Text.Json.Nodes;

namespace BowlBuster.Tests.Cli;

/// <summary>
/// A scripted game's recording written to a temporary directory, the way the harness writes one. Its captures hold the
/// heap descriptor but no bytes. It deletes only the directory it made.
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

        foreach ((string id, uint top) in game.CaptureTops) WriteCapture(id, top);
    }

    public string Path => directory.FullName;

    private string ManifestFile => System.IO.Path.Combine(directory.FullName, "manifest.json");

    public static ScriptedGame TwoLoads() => new ScriptedGame(ScriptedScenes.OriginStart)
        .Run(ScriptedScenes.Origin, 3)
        .Run(ScriptedScenes.Target, 4);

    private void WriteCapture(string id, uint top)
    {
        DirectoryInfo capture = directory.CreateSubdirectory(System.IO.Path.Combine("captures", id));
        JsonObject manifest = new()
        {
            ["id"] = id,
            ["heap"] = new JsonObject { ["depth"] = 0, ["states"] = new JsonArray(new JsonObject { ["cursor"] = top }) },
            ["ranges"] = new JsonObject { ["heap0"] = new JsonObject { ["address"] = top, ["length"] = 0, ["file"] = "heap0.bin" } },
        };

        File.WriteAllText(System.IO.Path.Combine(capture.FullName, "manifest.json"), manifest.ToJsonString());
        File.WriteAllBytes(System.IO.Path.Combine(capture.FullName, "heap0.bin"), []);
        File.WriteAllText(System.IO.Path.Combine(capture.FullName, "complete"), "");
    }

    public void Dispose() => directory.Delete(recursive: true);
}
