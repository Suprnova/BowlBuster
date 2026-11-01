using BowlBuster.Chains;
using BowlBuster.Loads;
using BowlBuster.Memory;
using System.Text.Json;

namespace BowlBuster.Recordings;

/// <summary>
/// Reads a recording from its manifest and its event stream.
/// </summary>
/// <remarks>
/// The manifest is one JSON document and the stream is JSON lines. Only the fields replay needs are read: other fields
/// and every other event are ignored, so a stream may carry anything else the harness observed. Nothing here checks that
/// a recording is right; that is replay validation's job.
/// </remarks>
public static class RecordingReader
{
    /// <summary>
    /// The newest manifest version this reader understands. Every earlier version is read as well.
    /// </summary>
    public const int SchemaVersion = 1;

    private const string CutoffTrigger = "cutoff";

    private static readonly HashSet<string> LoadEvents = ["alloc", "grow", "push", "pop", "model", "pool_free", "drawn", "capture", "scene_exit"];

    /// <summary>
    /// Reads a recording.
    /// </summary>
    /// <param name="manifest">The run manifest.</param>
    /// <param name="events">The event stream, one JSON document per line.</param>
    /// <returns>The recording, with each load's counter converted once to its load number.</returns>
    /// <exception cref="FormatException">
    /// The manifest or a line isn't valid JSON or lacks a field replay needs; the manifest's version is newer than
    /// <see cref="SchemaVersion"/>; or a load has no costumes in the manifest. The message names the manifest or the line.
    /// </exception>
    public static Recording Read(TextReader manifest, TextReader events)
    {
        ArgumentNullException.ThrowIfNull(manifest);
        ArgumentNullException.ThrowIfNull(events);

        Manifest run = ReadManifest(manifest);
        RecordingBuilder builder = new(run);
        int number = 0;

        while (events.ReadLine() is { } line)
        {
            number++;
            if (string.IsNullOrWhiteSpace(line)) continue;

            try
            {
                using JsonDocument document = JsonDocument.Parse(line);
                builder.Accept(document.RootElement);
            }
            catch (Exception exception) when (exception is JsonException or FormatException)
            {
                throw new FormatException($"Event line {number}: {exception.Message}", exception);
            }
        }

        return new Recording(run.Id, run.Platform, run.Basis, run.EventsDropped, builder.Finish());
    }

    private static Manifest ReadManifest(TextReader manifest)
    {
        try
        {
            using JsonDocument document = JsonDocument.Parse(manifest.ReadToEnd());
            JsonElement root = document.RootElement;

            int version = Int(root, "schema_version");
            if (version > SchemaVersion) throw new FormatException($"Schema version {version} is newer than this reader's {SchemaVersion}.");

            JsonElement basis = Field(root, "counter_basis");

            return new Manifest(
                Text(root, "run"),
                Text(Field(root, "disc"), "platform"),
                new CounterBasis(Text(basis, "boot_scene"), Int(basis, "boot_counter")),
                Int(root, "events_dropped"),
                ReadCostumeRows(root));
        }
        catch (Exception exception) when (exception is JsonException or FormatException)
        {
            throw new FormatException($"Manifest: {exception.Message}", exception);
        }
    }

    private static Dictionary<(int Segment, int Counter), Costumes> ReadCostumeRows(JsonElement manifest)
    {
        Dictionary<(int Segment, int Counter), Costumes> rows = [];

        foreach (JsonElement row in Rows(manifest, "loads"))
        {
            (int Segment, int Counter) load = (Int(row, "segment"), Int(row, "counter"));
            JsonElement costumes = Field(row, "costumes");

            if (!rows.TryAdd(load, new Costumes(OptionalText(costumes, "spongebob"), OptionalText(costumes, "patrick"))))
                throw new FormatException($"Segment {load.Segment}, counter {load.Counter} has two costumes rows.");
        }

        return rows;
    }

    private static HeapSnapshot ReadHeap(JsonElement heap)
    {
        int depth = Int(heap, "depth");
        HeapState[] states = [.. Rows(heap, "states").Take(depth + 1).Select(ReadState)];

        if (states.Length <= depth) throw new FormatException($"Depth {depth} has only {states.Length} depth states.");

        return new HeapSnapshot(states, Optional(heap, "last_block") is { } block ? new HeapBlock(UInt(block, "address"), UInt(block, "size")) : null);
    }

    private static HeapState ReadState(JsonElement state) => new(UInt(state, "cursor"), Int(state, "blocks"), UInt(state, "used"));

    private static HeapRequest? ReadRequest(string name, JsonElement line) => name switch
    {
        "model" => ReadModel(line),
        "pool_free" => new PoolFreeRequest(UInt(line, "instance")),
        _ when UInt(line, "heap") is not 0 => null,
        "alloc" => new AllocRequest(UInt(line, "size"), UInt(line, "alignment"), UInt(line, "address"), UInt(line, "caller"), ReadLayer(line)),
        "grow" => new GrowRequest(UInt(line, "size")),
        "push" => new PushRequest(),
        _ => new PopRequest(Int(line, "depth")),
    };

    private static PoolAllocRequest? ReadModel(JsonElement line) => Bool(line, "bypass")
        ? null
        : new PoolAllocRequest(UInt(line, "instance"), UInt(line, "caller"), Int(line, "nodes"), UInt(line, "flags"));

    private static LayerId? ReadLayer(JsonElement line) =>
        Optional(line, "layer") is { } layer ? new LayerId(Text(layer, "archive"), Int(layer, "layer")) : null;

    private static JsonElement? Optional(JsonElement element, string name) =>
        element.ValueKind is JsonValueKind.Object && element.TryGetProperty(name, out JsonElement value) && value.ValueKind is not JsonValueKind.Null
            ? value
            : null;

    private static JsonElement Field(JsonElement element, string name) =>
        Optional(element, name) ?? throw new FormatException($"The field '{name}' is missing.");

    private static JsonElement.ArrayEnumerator Rows(JsonElement element, string name)
    {
        JsonElement rows = Field(element, name);
        return rows.ValueKind is JsonValueKind.Array ? rows.EnumerateArray() : throw Invalid(name, "an array");
    }

    private static string Text(JsonElement element, string name)
    {
        JsonElement value = Field(element, name);
        return value.ValueKind is JsonValueKind.String && !string.IsNullOrWhiteSpace(value.GetString()) ? value.GetString()! : throw Invalid(name, "text");
    }

    private static string? OptionalText(JsonElement element, string name) => Optional(element, name) is null ? null : Text(element, name);

    private static uint UInt(JsonElement element, string name)
    {
        JsonElement value = Field(element, name);
        return value.ValueKind is JsonValueKind.Number && value.TryGetUInt32(out uint number) ? number : throw Invalid(name, "an unsigned 32-bit number");
    }

    private static int Int(JsonElement element, string name)
    {
        JsonElement value = Field(element, name);
        return value.ValueKind is JsonValueKind.Number && value.TryGetInt32(out int number) && number >= 0 ? number : throw Invalid(name, "a count");
    }

    private static bool Bool(JsonElement element, string name) => Field(element, name).ValueKind switch
    {
        JsonValueKind.True => true,
        JsonValueKind.False => false,
        _ => throw Invalid(name, "true or false"),
    };

    private static FormatException Invalid(string name, string expected) => new($"The field '{name}' is not {expected}.");

    private sealed record Manifest(string Id, string Platform, CounterBasis Basis, int EventsDropped, Dictionary<(int Segment, int Counter), Costumes> Costumes);

    private sealed class OpenLoad(LoadKey key, int segment, int counter, LoadNumber? load, HeapSnapshot start)
    {
        public int Segment { get; } = segment;

        public List<HeapRequest> Requests { get; } = [];

        public int? RequestsBeforeDrawn { get; set; }

        public string? CaptureId { get; set; }

        public bool ReachedExit { get; set; }

        public RecordedLoad Close() => new(
            key,
            counter,
            load,
            new HeapLog(start, Requests, RequestsBeforeDrawn is { } count ? new Cutoff(count, CaptureId) : null, ReachedExit));
    }

    private sealed class RecordingBuilder(Manifest manifest)
    {
        private readonly SortedDictionary<int, List<RecordedLoad>> segments = [];
        private OpenLoad? open;

        public void Accept(JsonElement line)
        {
            string name = Text(line, "event");

            if (name is "scene_init")
            {
                Close();
                open = Begin(line);
                return;
            }

            if (!LoadEvents.Contains(name)) return;

            int segment = Int(line, "segment");

            if (open is not { } load || load.Segment != segment)
            {
                Close();
                return;
            }

            switch (name)
            {
                case "drawn":
                    load.RequestsBeforeDrawn ??= load.Requests.Count;
                    break;

                case "capture":
                    if (Text(line, "trigger") is CutoffTrigger) load.CaptureId ??= Text(line, "id");
                    break;

                case "scene_exit":
                    load.ReachedExit = true;
                    break;

                default:
                    if (ReadRequest(name, line) is { } request) load.Requests.Add(request);
                    break;
            }
        }

        public IReadOnlyList<RecordingSegment> Finish()
        {
            Close();
            return [.. segments.Select(static segment => new RecordingSegment(segment.Key, segment.Value))];
        }

        private OpenLoad Begin(JsonElement line)
        {
            int segment = Int(line, "segment");
            int counter = Int(line, "counter");

            if (!manifest.Costumes.TryGetValue((segment, counter), out Costumes? costumes))
                throw new FormatException($"The manifest has no costumes for segment {segment}, counter {counter}.");

            LoadNumber? load = counter > manifest.Basis.BootCounter ? manifest.Basis.ToLoad(counter) : null;
            return new OpenLoad(new LoadKey(Text(line, "scene"), costumes), segment, counter, load, ReadHeap(Field(line, "heap")));
        }

        private void Close()
        {
            if (open is null) return;

            if (!segments.TryGetValue(open.Segment, out List<RecordedLoad>? loads))
                segments[open.Segment] = loads = [];

            loads.Add(open.Close());
            open = null;
        }
    }
}
