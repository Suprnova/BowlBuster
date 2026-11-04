using BowlBuster.Memory;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Replay;

namespace BowlBuster.Placement;

/// <summary>
/// Places a landing test's stale pointer: replays a recipe load's requests from the heap the live game has, and finds
/// where one of its blocks falls.
/// </summary>
/// <remarks>
/// A block is what an allocation of heap 0 with a size, or of a model pool, returns. A size-0 allocation, a grow, a
/// push, a pop and a free make none. The harness never computes <c>S</c> itself: this is where it comes from.
/// </remarks>
/// <param name="profile">The platform's constants.</param>
public sealed class Placer(PlatformProfile profile)
{
    private readonly PlatformProfile profile = profile ?? throw new ArgumentNullException(nameof(profile));

    /// <summary>
    /// Places a landing.
    /// </summary>
    /// <param name="recipe">The recording whose load stands in for the live one.</param>
    /// <param name="counter">The recipe load's counter.</param>
    /// <param name="segment">The segment that holds it, or <see langword="null"/> for the one segment that does.</param>
    /// <param name="live">Heap 0 as the live game's scene init found it.</param>
    /// <param name="op">The block's position in the load's request list.</param>
    /// <param name="delta">The signed byte offset of the pointer in the block.</param>
    /// <returns>The placement, or why there is none. A landing that can't be placed is a result, never an exception.</returns>
    public PlacementResult Place(ValidatedRecording recipe, int counter, int? segment, HeapSnapshot live, int op, int delta)
    {
        ArgumentNullException.ThrowIfNull(recipe);
        ArgumentNullException.ThrowIfNull(live);

        List<(int Segment, RecordedLoad Load)> found =
        [
            .. recipe.Recording.Segments
                .Where(candidate => segment is null || candidate.Index == segment)
                .SelectMany(candidate => candidate.Loads.Where(load => load.Counter == counter).Select(load => (candidate.Index, load))),
        ];

        return found switch
        {
            [] => new Unplaceable(segment is { } index ? $"Segment {index} holds no load {counter}." : $"No segment holds load {counter}."),
            [(_, RecordedLoad load)] => Replay(load, live, op, delta),
            _ => new AmbiguousLoad([.. found.Select(static pair => pair.Segment)]),
        };
    }

    private static HeapTop TopOf(GameHeap heap) => new(heap.Current.Cursor, heap.Depth);

    private static string? Unmade(HeapRequest request) => request switch
    {
        AllocRequest { Size: 0 } => "a size-0 allocation",
        AllocRequest or PoolAllocRequest => null,
        GrowRequest => "a grow",
        PushRequest => "a push",
        PopRequest => "a pop",
        _ => "a free",
    };

    private PlacementResult Replay(RecordedLoad load, HeapSnapshot live, int op, int delta)
    {
        IReadOnlyList<HeapRequest> requests = load.Heap.Requests;

        if (op < 0 || op >= requests.Count)
            return new NoBlock($"The load makes {requests.Count} request(s), so it has no op {op}.");

        if (Unmade(requests[op]) is { } kind)
            return new NoBlock($"Op {op} is {kind}, which makes no block.");

        int? cutoff = load.Heap.Cutoff?.RequestCount;
        int end = Math.Max(op + 1, cutoff ?? 0);
        uint? block = null;
        HeapTop? top = null;

        try
        {
            HeapReplayer replayer = new(profile, live.ToHeap(profile.Heap0));

            for (int index = 0; index < end; index++)
            {
                if (index == cutoff) top = TopOf(replayer.Heap);

                uint? returned = replayer.Apply(requests[index]);
                if (index == op) block = returned;
            }

            if (cutoff == end) top = TopOf(replayer.Heap);
        }
        catch (Exception exception) when (exception is InvalidOperationException or ArgumentException)
        {
            return new Unplaceable($"The load's requests don't replay from the live heap: {exception.Message}");
        }

        return block is 0 or null
            ? new NoBlock($"The live heap can't hold op {op}: the allocation fails.")
            : new Placed(unchecked(block.Value + (uint)delta), top);
    }
}
