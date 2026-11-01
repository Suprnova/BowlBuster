using BowlBuster.Memory;
using BowlBuster.Platforms;
using BowlBuster.Recordings;

namespace BowlBuster.Replay;

/// <summary>
/// Decides whether a recording can be used, by replaying every load from its own recorded start state.
/// </summary>
/// <remarks>
/// A load is checked against every address and instance it recorded, against the cutoff's capture when it has one, and
/// against the start state of the next load in its segment. The last load of a segment has no next load, so it takes
/// only the first two.
/// </remarks>
/// <param name="profile">The platform's constants.</param>
/// <param name="captures">Where to find captures, or <see langword="null"/> to check no cutoff against one.</param>
public sealed class ReplayValidator(PlatformProfile profile, ICaptureSource? captures = null)
{
    private readonly PlatformProfile profile = profile ?? throw new ArgumentNullException(nameof(profile));

    /// <summary>
    /// Validates a recording.
    /// </summary>
    /// <param name="recording">The recording.</param>
    /// <returns>The validated recording, or the first mismatch. A recording that doesn't replay is a result, never an exception.</returns>
    public RecordingValidation Validate(Recording recording)
    {
        ArgumentNullException.ThrowIfNull(recording);

        ReplayMismatch? mismatch = CheckRun(recording) ?? recording.Segments
            .Select(segment => CheckSegment(recording.Id, segment))
            .FirstOrDefault(static found => found is not null);

        return new RecordingValidation(mismatch is null ? new ValidatedRecording(recording) : null, mismatch);
    }

    private static (ReplayCheck Check, HeapDifference Difference)? Compare(HeapRequest request, uint? replayed) => request switch
    {
        AllocRequest alloc when alloc.Address != replayed => (ReplayCheck.ReturnedAddress, new HeapDifference("address", alloc.Address, replayed)),
        PoolAllocRequest instance when instance.Instance != replayed => (ReplayCheck.PoolInstance, new HeapDifference("instance", instance.Instance, replayed)),
        _ => null,
    };

    private ReplayMismatch? CheckRun(Recording recording)
    {
        if (recording.Platform != profile.Platform)
            return new ReplayMismatch(ReplayCheck.Platform, null, null, $"Recorded on {recording.Platform}, replayed on {profile.Platform}.");

        return recording.EventsDropped is 0
            ? null
            : new ReplayMismatch(ReplayCheck.DroppedEvents, null, null, $"The harness dropped {recording.EventsDropped} events.");
    }

    private ReplayMismatch? CheckSegment(string recordingId, RecordingSegment segment) => segment.Loads
        .Select((load, index) => CheckLoad(recordingId, segment.Index, load, segment.Loads.ElementAtOrDefault(index + 1)?.Heap.Start))
        .FirstOrDefault(static found => found is not null);

    private ReplayMismatch? CheckLoad(string recordingId, int segment, RecordedLoad load, HeapSnapshot? next)
    {
        IReadOnlyList<HeapRequest> requests = load.Heap.Requests;
        ILoadCapture? capture = load.Heap.Cutoff?.CaptureId is { } captureId ? captures?.Find(recordingId, captureId) : null;
        int? op = null;

        try
        {
            HeapReplayer replayer = new(profile, load.Heap.Start.ToHeap(profile.Heap0));

            for (op = 0; op <= requests.Count; op++)
            {
                if (op == load.Heap.Cutoff?.RequestCount && capture is not null && capture.HeapTop != replayer.Heap.Current.Cursor)
                {
                    HeapDifference cursor = new("cursor", capture.HeapTop, replayer.Heap.Current.Cursor);
                    return new ReplayMismatch(ReplayCheck.CutoffCursor, new MismatchSite(segment, load, null, HeapSnapshot.Of(replayer.Heap)), cursor, null);
                }

                if (op == requests.Count) break;

                if (Compare(requests[op.Value], replayer.Apply(requests[op.Value])) is { } found)
                    return new ReplayMismatch(found.Check, new MismatchSite(segment, load, op, StateBefore(load, op)), found.Difference, null);
            }

            HeapSnapshot end = HeapSnapshot.Of(replayer.Heap);

            return next?.FirstDifference(end) is { } difference
                ? new ReplayMismatch(ReplayCheck.EndState, new MismatchSite(segment, load, null, end), difference, null)
                : null;
        }
        catch (Exception exception) when (exception is InvalidOperationException or ArgumentException)
        {
            return new ReplayMismatch(ReplayCheck.IllegalRequest, new MismatchSite(segment, load, op, StateBefore(load, op)), null, exception.Message);
        }
    }

    private HeapSnapshot StateBefore(RecordedLoad load, int? op)
    {
        if (op is not { } count) return load.Heap.Start;

        HeapReplayer replayer = new(profile, load.Heap.Start.ToHeap(profile.Heap0));
        foreach (HeapRequest request in load.Heap.Requests.Take(count))
        {
            replayer.Apply(request);
        }

        return HeapSnapshot.Of(replayer.Heap);
    }
}
