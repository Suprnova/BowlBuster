using BowlBuster.Memory;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Replay;
using BowlBuster.Tests.Recordings;

namespace BowlBuster.Tests.Replay;

public class ReplayValidatorTests
{
    private const string OriginCapture = "origin-cutoff";
    private const string TargetCapture = "target-cutoff";

    private const int OriginLoad = 0;
    private const int TargetLoad = 1;

    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;

    private readonly ScriptedGame game;
    private readonly Recording recording;
    private readonly ReplayValidator validator;

    public ReplayValidatorTests()
    {
        game = new ScriptedGame(ScriptedScenes.OriginStart)
            .Run(ScriptedScenes.Origin, 3, capture: OriginCapture)
            .Run(ScriptedScenes.Target, 4, capture: TargetCapture);
        recording = game.Recording;
        validator = new ReplayValidator(Platform, new FakeCaptures(game.CaptureTops));
    }

    private static Recording WithLoad(Recording recording, int index, Func<RecordedLoad, RecordedLoad> change) => recording with
    {
        Segments = [new RecordingSegment(0, [.. recording.Segments[0].Loads.Select((load, position) => position == index ? change(load) : load)])],
    };

    private static RecordedLoad WithRequests(RecordedLoad load, IEnumerable<HeapRequest> requests) =>
        load with { Heap = load.Heap with { Requests = [.. requests] } };

    private static RecordedLoad WithRequest(RecordedLoad load, int op, HeapRequest request) =>
        WithRequests(load, load.Heap.Requests.Select((old, position) => position == op ? request : old));

    private static RecordedLoad WithStart(RecordedLoad load, HeapSnapshot start) =>
        load with { Heap = load.Heap with { Start = start } };

    private static RecordedLoad CutBeforeExit(RecordedLoad load) => load with
    {
        Heap = load.Heap with { Requests = [.. load.Heap.Requests.Take(load.Heap.Cutoff!.Value.RequestCount)], ReachedExit = false },
    };

    private static AllocRequest AllocAt(RecordedLoad load, int op) => (AllocRequest)load.Heap.Requests[op];

    private ReplayMismatch Rejected(Recording tampered)
    {
        RecordingValidation validation = validator.Validate(tampered);

        Assert.False(validation.IsAccepted);
        Assert.Null(validation.Recording);
        return validation.Rejection;
    }

    private RecordingValidation ValidateLoad(int index, Func<RecordedLoad, RecordedLoad> change) =>
        validator.Validate(WithLoad(recording, index, change));

    private Recording WithOriginAddress(int op, uint address) =>
        WithLoad(recording, OriginLoad, load => WithRequest(load, op, AllocAt(load, op) with { Address = address }));

    [Fact]
    public void Validate_UntamperedRecordingWithCaptures_IsAccepted()
    {
        RecordingValidation validation = validator.Validate(recording);

        Assert.True(validation.IsAccepted);
        Assert.Null(validation.Rejection);
        Assert.Same(recording, validation.Recording.Recording);
    }

    [Fact]
    public void Validate_UntamperedRecordingWithNoCaptureSource_IsAccepted() =>
        Assert.True(new ReplayValidator(Platform).Validate(recording).IsAccepted);

    [Fact]
    public void Validate_CaptureTheSourceDoesNotHave_SkipsTheCutoffCheck()
    {
        ReplayValidator noCaptures = new(Platform, new FakeCaptures(new Dictionary<string, uint>()));

        Assert.True(noCaptures.Validate(recording).IsAccepted);
    }

    [Fact]
    public void Validate_WrongAddress_ReportsTheOpWithBothAddressesAndTheStateBeforeIt()
    {
        ReplayMismatch mismatch = Rejected(WithOriginAddress(8, 0x747C80));

        Assert.Equal(ReplayCheck.ReturnedAddress, mismatch.Check);
        MismatchSite site = Assert.NotNull(mismatch.Site);
        Assert.Equal(0, site.Segment);
        Assert.Equal("ORIG", site.Load.Key.Scene);
        Assert.Equal(3, site.Load.Counter);
        Assert.Equal(8, site.Op);
        Assert.Equal(new HeapDifference("address", 0x747C80, 0x747C40), mismatch.Difference);
        Assert.Equal(4, site.Heap.Depth);
        Assert.Equal(0x747BFCu, site.Heap.States[^1].Cursor);
    }

    [Fact]
    public void Validate_WrongAddress_NamesTheRequest()
    {
        ReplayMismatch mismatch = Rejected(WithOriginAddress(8, 0x747C80));

        Assert.Equal(new AllocRequest(0x2000, 0x40, 0x747C80, ScriptedScenes.LayerSite, new LayerId("ORIG", 0)), mismatch.Site?.Request);
    }

    [Fact]
    public void Validate_WrongPoolInstance_ReportsThePoolInstance()
    {
        Recording tampered = WithLoad(recording, OriginLoad, load => WithRequest(load, 13, new PoolAllocRequest(0x73B21C, ScriptedScenes.SphereSite, 0, 0)));

        ReplayMismatch mismatch = Rejected(tampered);

        Assert.Equal(ReplayCheck.PoolInstance, mismatch.Check);
        Assert.Equal(13, mismatch.Site?.Op);
        Assert.Equal(new HeapDifference("instance", 0x73B21C, 0x73B17C), mismatch.Difference);
    }

    [Fact]
    public void Validate_ExitPopMissing_ReportsTheEndStatesDepth()
    {
        Recording tampered = WithLoad(recording, OriginLoad, static load => WithRequests(load, load.Heap.Requests.SkipLast(1)));

        ReplayMismatch mismatch = Rejected(tampered);

        Assert.Equal(ReplayCheck.EndState, mismatch.Check);
        Assert.Null(mismatch.Site?.Op);
        Assert.Equal(new HeapDifference("depth", 1, 4), mismatch.Difference);
    }

    [Fact]
    public void Validate_NextLoadStartsFromAnotherCursor_ReportsTheEarlierLoad()
    {
        HeapSnapshot start = ScriptedScenes.TargetStart with { States = [ScriptedScenes.TargetStart.States[0], new HeapState(0x6E6F1C, 501, 0x126EE8)] };

        ReplayMismatch mismatch = Rejected(WithLoad(recording, TargetLoad, load => WithStart(load, start)));

        Assert.Equal(ReplayCheck.EndState, mismatch.Check);
        Assert.Equal("ORIG", mismatch.Site?.Load.Key.Scene);
        Assert.Equal(new HeapDifference("states[1].cursor", 0x6E6F1C, 0x6E6F18), mismatch.Difference);
    }

    [Fact]
    public void Validate_NextLoadStartsFromAnotherLastBlock_ReportsTheLastBlock()
    {
        HeapSnapshot start = ScriptedScenes.TargetStart with { LastBlock = new HeapBlock(0x749D50, 0x24) };

        ReplayMismatch mismatch = Rejected(WithLoad(recording, TargetLoad, load => WithStart(load, start)));

        Assert.Equal(new HeapDifference("last_block.size", 0x24, 0x20), mismatch.Difference);
    }

    [Fact]
    public void Validate_CaptureTopOffTheCursor_ReportsTheCutoffCursor()
    {
        Dictionary<string, uint> tops = new(game.CaptureTops) { [OriginCapture] = 0x749D44 };
        ReplayValidator offset = new(Platform, new FakeCaptures(tops));

        ReplayMismatch? mismatch = offset.Validate(recording).Rejection;

        Assert.Equal(ReplayCheck.CutoffCursor, mismatch?.Check);
        Assert.Equal(new HeapDifference("cursor", 0x749D44, 0x749D40), mismatch?.Difference);
        Assert.Equal(0x749D40u, mismatch?.Site?.Heap.States[^1].Cursor);
    }

    [Fact]
    public void Validate_CutoffAfterTheLastRequest_IsStillChecked()
    {
        Dictionary<string, uint> tops = new(game.CaptureTops) { [TargetCapture] = 0x798770 };
        ReplayValidator offset = new(Platform, new FakeCaptures(tops));

        RecordingValidation validation = offset.Validate(WithLoad(recording, TargetLoad, CutBeforeExit));

        Assert.Equal(ReplayCheck.CutoffCursor, validation.Rejection?.Check);
    }

    [Fact]
    public void Validate_TwoMismatches_ReportsTheEarlierOne()
    {
        Recording tampered = WithLoad(WithOriginAddress(8, 0x747C80), OriginLoad, load => WithRequest(load, 5, AllocAt(load, 5) with { Address = 0 }));

        ReplayMismatch mismatch = Rejected(tampered);

        Assert.Equal(5, mismatch.Site?.Op);
    }

    [Fact]
    public void Validate_MismatchesInTwoLoads_ReportsTheEarlierLoad()
    {
        Recording tampered = WithLoad(WithOriginAddress(8, 0x747C80), TargetLoad, load => WithRequest(load, 0, AllocAt(load, 0) with { Address = 0 }));

        ReplayMismatch mismatch = Rejected(tampered);

        Assert.Equal("ORIG", mismatch.Site?.Load.Key.Scene);
    }

    [Fact]
    public void Validate_LoadWithNoRequestsMidSegment_FailsTheEndState()
    {
        RecordingValidation validation = ValidateLoad(OriginLoad, static load => WithRequests(load, []));

        Assert.Equal(ReplayCheck.EndState, validation.Rejection?.Check);
    }

    [Fact]
    public void Validate_LastLoadWithNoRequestsAndNoCutoff_IsAccepted()
    {
        RecordingValidation validation = ValidateLoad(TargetLoad, static load => load with { Heap = load.Heap with { Requests = [], Cutoff = null } });

        Assert.True(validation.IsAccepted);
    }

    [Fact]
    public void Validate_LastLoadDrawnWithNoHeapLogButACapture_FailsTheCutoffCursor()
    {
        RecordingValidation validation = ValidateLoad(
            TargetLoad,
            static load => load with { Heap = load.Heap with { Requests = [], Cutoff = new Cutoff(0, TargetCapture) } });

        Assert.Equal(ReplayCheck.CutoffCursor, validation.Rejection?.Check);
    }

    [Fact]
    public void Validate_LastLoadCutBeforeItsExit_IsAccepted() =>
        Assert.True(ValidateLoad(TargetLoad, CutBeforeExit).IsAccepted);

    [Fact]
    public void Validate_LoadCutBeforeItsExitMidSegment_FailsTheEndState()
    {
        RecordingValidation validation = ValidateLoad(OriginLoad, CutBeforeExit);

        Assert.Equal(ReplayCheck.EndState, validation.Rejection?.Check);
    }

    [Fact]
    public void Validate_TwoSegmentsRepeatingCounters_ExemptsEachSegmentsLastLoad()
    {
        Recording resumed = new ScriptedGame(ScriptedScenes.OriginStart)
            .Run(ScriptedScenes.Origin, 3)
            .Run(ScriptedScenes.Target, 4)
            .BeginSegment(ScriptedScenes.OriginStart)
            .Run(ScriptedScenes.Origin, 3)
            .Run(ScriptedScenes.Target, 4)
            .Recording;

        Assert.True(validator.Validate(resumed).IsAccepted);
    }

    [Fact]
    public void Validate_MismatchInALaterSegment_NamesThatSegment()
    {
        Recording resumed = new ScriptedGame(ScriptedScenes.OriginStart)
            .Run(ScriptedScenes.Origin, 3)
            .BeginSegment(ScriptedScenes.OriginStart)
            .Run(ScriptedScenes.Origin, 3)
            .Recording;
        RecordedLoad load = resumed.Segments[1].Loads[0];
        RecordedLoad tampered = WithRequest(load, 0, AllocAt(load, 0) with { Address = 0 });

        ReplayMismatch mismatch = Rejected(resumed with { Segments = [resumed.Segments[0], new RecordingSegment(1, [tampered])] });

        Assert.Equal(1, mismatch.Site?.Segment);
    }

    [Fact]
    public void Validate_PopBelowNoDepth_IsAnIllegalRequestNotAnException()
    {
        ReplayMismatch mismatch = Rejected(WithLoad(recording, OriginLoad, static load => WithRequest(load, 1, new PopRequest(9))));

        Assert.Equal(ReplayCheck.IllegalRequest, mismatch.Check);
        Assert.Equal(1, mismatch.Site?.Op);
        Assert.False(string.IsNullOrEmpty(mismatch.Detail));
        Assert.Null(mismatch.Difference);
    }

    [Fact]
    public void Validate_GrowWithNoLastBlock_IsAnIllegalRequest()
    {
        HeapSnapshot start = ScriptedScenes.OriginStart with { LastBlock = null };

        ReplayMismatch mismatch = Rejected(WithLoad(recording, OriginLoad, load => WithRequest(WithStart(load, start), 0, new GrowRequest(4))));

        Assert.Equal(ReplayCheck.IllegalRequest, mismatch.Check);
        Assert.Equal(0, mismatch.Site?.Op);
    }

    [Fact]
    public void Validate_AlignmentThatIsNoPowerOfTwo_IsAnIllegalRequest()
    {
        Recording tampered = WithLoad(recording, OriginLoad, load => WithRequest(load, 2, AllocAt(load, 2) with { Alignment = 0x30 }));

        Assert.Equal(ReplayCheck.IllegalRequest, Rejected(tampered).Check);
    }

    [Fact]
    public void Validate_StartDeeperThanTheHeapHasDepths_IsAnIllegalRequestAtNoOp()
    {
        HeapSnapshot start = new([.. Enumerable.Repeat(new HeapState(0x6E6C48, 0, 0), Platform.Heap0.DepthCount + 1)], null);

        ReplayMismatch mismatch = Rejected(WithLoad(recording, OriginLoad, load => WithStart(load, start)));

        Assert.Equal(ReplayCheck.IllegalRequest, mismatch.Check);
        Assert.Null(mismatch.Site?.Op);
        Assert.Same(start, mismatch.Site?.Heap);
    }

    [Fact]
    public void Validate_OtherPlatform_RejectsBeforeReplaying()
    {
        ReplayMismatch mismatch = Rejected(WithOriginAddress(8, 0x747C80) with { Platform = "ps2" });

        Assert.Equal(ReplayCheck.Platform, mismatch.Check);
        Assert.Null(mismatch.Site);
        Assert.Contains("ps2", mismatch.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Validate_DroppedEvents_RejectsBeforeReplaying()
    {
        ReplayMismatch mismatch = Rejected(WithOriginAddress(8, 0x747C80) with { EventsDropped = 1 });

        Assert.Equal(ReplayCheck.DroppedEvents, mismatch.Check);
        Assert.Null(mismatch.Site);
    }

    [Fact]
    public void Validate_RecordingWithNoLoads_IsAccepted()
    {
        Recording empty = recording with { Segments = [] };

        Assert.True(validator.Validate(empty).IsAccepted);
    }

    [Fact]
    public void ToString_WrongAddress_HoldsTheLoadOpAndBothAddresses()
    {
        string line = Rejected(WithOriginAddress(8, 0x747C80)).ToString();

        Assert.StartsWith("ORIG (segment 0, counter 3), op 8: ReturnedAddress", line, StringComparison.Ordinal);
        Assert.EndsWith("address recorded 0x747C80, replayed 0x747C40", line, StringComparison.Ordinal);
    }

    [Fact]
    public void ToString_NoSite_HoldsTheCheckAndDetail()
    {
        string line = Rejected(recording with { Platform = "ps2" }).ToString();

        Assert.Equal("Platform: Recorded on ps2, replayed on xbox.", line);
    }
}
