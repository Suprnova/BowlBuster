using BowlBuster.Chains;
using BowlBuster.Loads;
using BowlBuster.Memory;
using BowlBuster.Recordings;

namespace BowlBuster.Tests.Recordings;

public class RecordingReaderTests
{
    private const string SceneInitLine =
        """{"seq":1,"segment":0,"frame":120,"event":"scene_init","scene":"ORIG","caller":338064,"counter":3,"heap":{"depth":1,"states":[{"cursor":6029360,"blocks":0,"used":0},{"cursor":7236680,"blocks":500,"used":1207320}],"last_block":{"address":7235984,"size":696}}}""";

    private const string AllocLine =
        """{"seq":2,"segment":0,"frame":120,"event":"alloc","heap":0,"size":696,"alignment":0,"address":7236704,"caller":468592}""";

    private const string Drawn = """{"event":"drawn","segment":0}""";

    private const string Push = """{"event":"push","segment":0,"heap":0}""";

    private const string PushInSegmentOne = """{"event":"push","segment":1,"heap":0}""";

    private readonly string manifest;

    public RecordingReaderTests() => manifest = Manifest();

    private static string Manifest(string bootScene = "MNUS", int bootCounter = 1, string rows = """{"segment":0,"counter":3,"costumes":{"spongebob":"Mermaid Man","patrick":null}}""") =>
        $$"""
        { "schema_version": 1, "run": "synthetic-1", "disc": { "platform": "xbox" },
          "counter_basis": { "boot_scene": "{{bootScene}}", "boot_counter": {{bootCounter}} }, "events_dropped": 0,
          "loads": [ {{rows}} ] }
        """;

    private static string SceneInit(int segment, int counter, string scene = "ORIG") =>
        $$$"""{"event":"scene_init","segment":{{{segment}}},"scene":"{{{scene}}}","counter":{{{counter}}},"heap":{"depth":0,"states":[{"cursor":4096,"blocks":0,"used":0}],"last_block":null}}""";

    private static string Row(int segment, int counter, string costume = "null") =>
        $$$"""{"segment":{{{segment}}},"counter":{{{counter}}},"costumes":{"spongebob":{{{costume}}},"patrick":null}}""";

    private static Recording Read(string manifest, params string[] lines) =>
        RecordingReader.Read(new StringReader(manifest), new StringReader(string.Join('\n', lines)));

    private RecordedLoad ReadLoad(params string[] lines) => Read(manifest, [SceneInitLine, .. lines]).Segments[0].Loads[0];

    [Fact]
    public void Read_Manifest_TakesTheRunsIdentityAndBasis()
    {
        Recording recording = Read(Manifest("MNUS", 1), SceneInitLine);

        Assert.Equal("synthetic-1", recording.Id);
        Assert.Equal("xbox", recording.Platform);
        Assert.Equal(CounterBasis.Retail, recording.Basis);
        Assert.Equal(0, recording.EventsDropped);
    }

    [Fact]
    public void Read_SampleSceneInit_TakesTheHeapStateSceneAndCounter()
    {
        RecordedLoad load = ReadLoad();

        Assert.Equal("ORIG", load.Key.Scene);
        Assert.Equal(3, load.Counter);
        Assert.Equal(1, load.Heap.Start.Depth);
        Assert.Equal(new HeapState(0x5C0030, 0, 0), load.Heap.Start.States[0]);
        Assert.Equal(new HeapState(0x6E6C48, 500, 0x126C18), load.Heap.Start.States[1]);
        Assert.Equal(new HeapBlock(0x6E6990, 0x2B8), load.Heap.Start.LastBlock);
    }

    [Fact]
    public void Read_SampleAlloc_TakesEveryField()
    {
        RecordedLoad load = ReadLoad(AllocLine);

        Assert.Equal(new AllocRequest(0x2B8, 0, 0x6E6C60, 0x72670), Assert.Single(load.Heap.Requests));
    }

    [Fact]
    public void Read_AllocWithALayer_TakesTheArchiveAndLayer()
    {
        const string alloc = """{"event":"alloc","segment":0,"heap":0,"size":64,"alignment":64,"address":8192,"caller":1648736,"layer":{"archive":"PLAY","layer":2}}""";

        RecordedLoad load = ReadLoad(alloc);

        Assert.Equal(new LayerId("PLAY", 2), ((AllocRequest)load.Heap.Requests[0]).Layer);
    }

    [Fact]
    public void Read_EachRequestKind_BecomesItsRequest()
    {
        string[] lines =
        [
            """{"event":"grow","segment":0,"heap":0,"size":256}""",
            Push,
            """{"event":"pop","segment":0,"heap":0,"depth":1}""",
            """{"event":"model","segment":0,"bypass":false,"instance":7582076,"nodes":3,"flags":64,"caller":717885}""",
            """{"event":"pool_free","segment":0,"instance":7582076}""",
        ];

        RecordedLoad load = ReadLoad(lines);

        Assert.Equal(
            [new GrowRequest(0x100), new PushRequest(), new PopRequest(1), new PoolAllocRequest(0x73B17C, 0xAF43D, 3, 0x40), new PoolFreeRequest(0x73B17C)],
            load.Heap.Requests);
    }

    [Fact]
    public void Read_EventsThatAreNotRequests_TakeNoOp()
    {
        string[] lines =
        [
            """{"event":"model","segment":0,"bypass":true,"instance":7582076,"nodes":3,"flags":0}""",
            """{"event":"alloc","segment":0,"heap":1,"size":64,"alignment":0,"address":8192,"caller":4096}""",
            """{"event":"entity","segment":0,"address":7236704}""",
            """{"event":"from_a_later_harness","anything":[1,2,3]}""",
            AllocLine,
        ];

        RecordedLoad load = ReadLoad(lines);

        Assert.Equal(new AllocRequest(0x2B8, 0, 0x6E6C60, 0x72670), Assert.Single(load.Heap.Requests));
    }

    [Fact]
    public void Read_SizeZeroAlloc_TakesAnOp()
    {
        const string zero = """{"event":"alloc","segment":0,"heap":0,"size":0,"alignment":0,"address":3735928559,"caller":4096}""";

        RecordedLoad load = ReadLoad(zero, AllocLine);

        Assert.Equal(2, load.Heap.Requests.Count);
    }

    [Fact]
    public void Read_PopAfterTheSceneExit_StaysInTheLoadsRequests()
    {
        string[] lines = [AllocLine, """{"event":"scene_exit","segment":0}""", """{"event":"pop","segment":0,"heap":0,"depth":1}"""];

        RecordedLoad load = ReadLoad(lines);

        Assert.True(load.Heap.ReachedExit);
        Assert.Equal(new PopRequest(1), load.Heap.Requests[^1]);
    }

    [Fact]
    public void Read_StreamThatStopsBeforeTheExit_HasNotReachedIt() => Assert.False(ReadLoad(AllocLine).Heap.ReachedExit);

    [Fact]
    public void Read_Requests_EndAtTheNextSceneInit()
    {
        string rows = $"{Row(0, 3)},{Row(0, 4)}";

        Recording recording = Read(Manifest(rows: rows), SceneInit(0, 3), Push, SceneInit(0, 4), Push, Push);

        Assert.Single(recording.Segments[0].Loads[0].Heap.Requests);
        Assert.Equal(2, recording.Segments[0].Loads[1].Heap.Requests.Count);
    }

    [Fact]
    public void Read_FirstDrawn_IsTheCutoffAndALaterOneChangesNothing()
    {
        RecordedLoad load = ReadLoad(Push, Push, Drawn, Push, Drawn);

        Assert.Equal(2, load.Heap.Cutoff?.RequestCount);
    }

    [Fact]
    public void Read_NoDrawn_HasNoCutoff() => Assert.Null(ReadLoad(Push).Heap.Cutoff);

    [Fact]
    public void Read_DrawnBeforeAnyRequest_IsCutoffZero() => Assert.Equal(0, ReadLoad(Drawn, Push).Heap.Cutoff?.RequestCount);

    [Theory]
    [InlineData("""{"event":"capture","segment":0,"id":"c-1","trigger":"cutoff"}""", "c-1")]
    [InlineData("""{"event":"capture","segment":0,"id":"c-2","trigger":"crash"}""", null)]
    public void Read_Capture_IsKeptOnlyForTheCutoffTrigger(string line, string? expected) =>
        Assert.Equal(expected, ReadLoad(Drawn, line).Heap.Cutoff?.CaptureId);

    [Fact]
    public void Read_CaptureBeforeTheDrawn_StillBelongsToTheCutoff()
    {
        const string capture = """{"event":"capture","segment":0,"id":"c-1","trigger":"cutoff"}""";

        Cutoff? cutoff = ReadLoad(capture, Push, Drawn).Heap.Cutoff;

        Assert.Equal(new Cutoff(1, "c-1"), cutoff);
    }

    [Fact]
    public void Read_CaptureWithNoDrawn_LeavesNoCutoff()
    {
        const string capture = """{"event":"capture","segment":0,"id":"c-1","trigger":"cutoff"}""";

        Assert.Null(ReadLoad(capture).Heap.Cutoff);
    }

    [Theory]
    [InlineData(1, 1, null)]
    [InlineData(1, 2, 1)]
    [InlineData(1, 4, 3)]
    [InlineData(5, 6, 1)]
    [InlineData(5, 3, null)]
    public void Read_Counter_ConvertsToALoadOnTheManifestsBasis(int bootCounter, int counter, int? expected)
    {
        Recording recording = Read(Manifest("MNUS", bootCounter, Row(0, counter)), SceneInit(0, counter, "MNUS"));

        RecordedLoad load = recording.Segments[0].Loads[0];
        Assert.Equal(counter, load.Counter);
        Assert.Equal(expected, load.Load?.Value);
    }

    [Fact]
    public void Read_FirstSceneAtTheBootCounter_IsKeptWithNoLoadNumber()
    {
        Recording recording = Read(Manifest(rows: Row(0, 1)), SceneInit(0, 1, "BB02"));

        Assert.Null(recording.Segments[0].Loads[0].Load);
        Assert.Equal("BB02", recording.Segments[0].Loads[0].Key.Scene);
    }

    [Fact]
    public void Read_TwoSegmentsRepeatingACounter_KeepsThemApartWithTheirOwnCostumes()
    {
        string rows = $"{Row(0, 3, "\"Mermaid Man\"")},{Row(1, 3, "\"Plain Sponge\"")}";

        Recording recording = Read(Manifest(rows: rows), SceneInit(0, 3), Push, SceneInit(1, 3), PushInSegmentOne, PushInSegmentOne);

        Assert.Equal([0, 1], recording.Segments.Select(static segment => segment.Index));
        Assert.Equal("Mermaid Man", recording.Segments[0].Loads[0].Key.Costumes.Spongebob);
        Assert.Equal("Plain Sponge", recording.Segments[1].Loads[0].Key.Costumes.Spongebob);
        Assert.Single(recording.Segments[0].Loads[0].Heap.Requests);
        Assert.Equal(2, recording.Segments[1].Loads[0].Heap.Requests.Count);
    }

    [Fact]
    public void Read_RequestsBeforeASegmentsFirstSceneInit_AreDropped()
    {
        string rows = $"{Row(0, 3)},{Row(1, 4)}";
        const string orphan = """{"event":"pop","segment":1,"heap":0,"depth":9}""";

        Recording recording = Read(Manifest(rows: rows), SceneInit(0, 3), Push, orphan, orphan, SceneInit(1, 4), PushInSegmentOne);

        Assert.Single(recording.Segments[0].Loads[0].Heap.Requests);
        Assert.Single(recording.Segments[1].Loads[0].Heap.Requests);
    }

    [Fact]
    public void Read_RequestsBeforeAnySceneInit_AreDropped()
    {
        Recording recording = Read(Manifest(rows: Row(0, 3)), Push, SceneInit(0, 3));

        Assert.Empty(recording.Segments[0].Loads[0].Heap.Requests);
    }

    [Fact]
    public void Read_NoEvents_HasNoSegments() => Assert.Empty(Read(manifest).Segments);

    [Fact]
    public void Read_TwelveDepthStates_KeepsOnlyThoseUpToTheDepth()
    {
        string states = string.Join(',', Enumerable.Range(0, 12).Select(static depth => $$"""{"cursor":{{depth}},"blocks":0,"used":0}"""));
        string line = $$$"""{"event":"scene_init","segment":0,"scene":"ORIG","counter":3,"heap":{"depth":2,"states":[{{{states}}}]}}""";

        RecordedLoad load = Read(manifest, line).Segments[0].Loads[0];

        Assert.Equal(2, load.Heap.Start.Depth);
        Assert.Equal([0u, 1u, 2u], load.Heap.Start.States.Select(static state => state.Cursor));
        Assert.Null(load.Heap.Start.LastBlock);
    }

    [Fact]
    public void Read_NoCostumeEquipped_MatchesTheEmptyCostumes()
    {
        Recording recording = Read(Manifest(rows: Row(0, 3)), SceneInit(0, 3));

        Assert.Equal(new LoadKey("ORIG", Costumes.None), recording.Segments[0].Loads[0].Key);
    }

    [Fact]
    public void Read_BlankLine_IsSkipped() => Assert.Single(ReadLoad(string.Empty, Push).Heap.Requests);

    [Fact]
    public void Read_ScriptedRun_ReadsAsTheRunWrote()
    {
        ScriptedGame game = new ScriptedGame(ScriptedScenes.OriginStart)
            .Run(ScriptedScenes.Origin, 3, new Costumes("Mermaid Man", null), "origin-cutoff")
            .Run(ScriptedScenes.Target, 4);

        Recording read = Read(game.ManifestText, game.EventText);

        foreach ((RecordedLoad actual, RecordedLoad expected) in read.Segments[0].Loads.Zip(game.Recording.Segments[0].Loads))
        {
            Assert.Equal(expected.Key, actual.Key);
            Assert.Equal(expected.Load, actual.Load);
            Assert.Equal(expected.Heap.Requests, actual.Heap.Requests);
            Assert.Equal(expected.Heap.Cutoff?.RequestCount, actual.Heap.Cutoff?.RequestCount);
            Assert.Equal(expected.Heap.Cutoff?.CaptureId, actual.Heap.Cutoff?.CaptureId);
            Assert.Equal(expected.Heap.ReachedExit, actual.Heap.ReachedExit);
            Assert.Null(actual.Heap.Start.FirstDifference(expected.Heap.Start));
        }
    }

    [Fact]
    public void Read_InvalidJsonOnALine_NamesTheLine()
    {
        FormatException exception = Assert.Throws<FormatException>(() => Read(manifest, SceneInitLine, "{not json"));

        Assert.Contains("line 2", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Read_RequestMissingAField_NamesTheLineAndTheField()
    {
        const string alloc = """{"event":"alloc","segment":0,"heap":0,"alignment":0,"address":8192,"caller":4096}""";

        FormatException exception = Assert.Throws<FormatException>(() => Read(manifest, SceneInitLine, alloc));

        Assert.Contains("line 2", exception.Message, StringComparison.Ordinal);
        Assert.Contains("'size'", exception.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("""{"event":"alloc","segment":0,"heap":0,"size":"64","alignment":0,"address":8192,"caller":4096}""")]
    [InlineData("""{"event":"alloc","segment":0,"heap":0,"size":-1,"alignment":0,"address":8192,"caller":4096}""")]
    [InlineData("""{"event":"pop","segment":0,"heap":0,"depth":-1}""")]
    [InlineData("""{"event":"model","segment":0,"bypass":"no","instance":1,"nodes":0,"flags":0,"caller":1}""")]
    [InlineData("""[1,2,3]""")]
    public void Read_FieldOfTheWrongKind_Throws(string line) =>
        Assert.Throws<FormatException>(() => Read(manifest, SceneInitLine, line));

    [Fact]
    public void Read_NewerSchemaVersion_Throws()
    {
        string newer = manifest.Replace("\"schema_version\": 1", "\"schema_version\": 2", StringComparison.Ordinal);

        FormatException exception = Assert.Throws<FormatException>(() => Read(newer));

        Assert.Contains("version 2", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Read_InvalidManifest_NamesTheManifest()
    {
        FormatException exception = Assert.Throws<FormatException>(() => Read("{not json"));

        Assert.StartsWith("Manifest:", exception.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("run")]
    [InlineData("disc")]
    [InlineData("counter_basis")]
    [InlineData("events_dropped")]
    [InlineData("loads")]
    public void Read_ManifestMissingAField_Throws(string field)
    {
        string renamed = manifest.Replace($"\"{field}\"", "\"renamed\"", StringComparison.Ordinal);

        FormatException exception = Assert.Throws<FormatException>(() => Read(renamed));

        Assert.Contains($"'{field}'", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Read_LoadWithNoCostumesRow_NamesTheLoad()
    {
        FormatException exception = Assert.Throws<FormatException>(() => Read(manifest, SceneInit(2, 7)));

        Assert.Contains("segment 2, counter 7", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Read_TwoCostumesRowsForALoad_Throws()
    {
        string rows = $"{Row(0, 3)},{Row(0, 3)}";

        Assert.Throws<FormatException>(() => Read(Manifest(rows: rows)));
    }

    [Fact]
    public void Read_BlankCostume_Throws() =>
        Assert.Throws<FormatException>(() => Read(Manifest(rows: Row(0, 3, "\"  \""))));

    [Fact]
    public void Read_FewerDepthStatesThanTheDepth_Throws()
    {
        const string line = """{"event":"scene_init","segment":0,"scene":"ORIG","counter":3,"heap":{"depth":1,"states":[{"cursor":0,"blocks":0,"used":0}]}}""";

        Assert.Throws<FormatException>(() => Read(manifest, line));
    }
}
