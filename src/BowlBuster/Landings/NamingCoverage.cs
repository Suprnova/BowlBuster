using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Replay;

namespace BowlBuster.Landings;

/// <summary>
/// A live block at a load's cutoff, and how far its bytes are named.
/// </summary>
/// <param name="Block">The block, at its recorded address.</param>
/// <param name="First">The name of its first word.</param>
/// <param name="Bytes">The block's bytes by how far their word's name reaches. A depth no word reaches is absent.</param>
public sealed record BlockNaming(PlacedBlock Block, RegionName First, IReadOnlyDictionary<NamingDepth, uint> Bytes);

/// <summary>
/// The live blocks a load allocated before its cutoff, named.
/// </summary>
/// <param name="Segment">The load's segment.</param>
/// <param name="Load">The load.</param>
/// <param name="Blocks">Its blocks live at the cutoff, in address order.</param>
public sealed record LoadNaming(int Segment, RecordedLoad Load, IReadOnlyList<BlockNaming> Blocks);

/// <summary>
/// Measures how much of a recording's heap the <see cref="RegionNamer"/> names: every word of every block a load
/// allocated before its cutoff and still holds there, for each load with a cutoff capture.
/// </summary>
/// <remarks>
/// Memory below the load's start (an earlier load's leaked entity, the boot scene's blocks) and the headers and padding
/// between blocks aren't counted.
/// </remarks>
/// <param name="profile">The platform's constants.</param>
/// <param name="namer">The namer to measure.</param>
/// <param name="captures">The recording's captures.</param>
public sealed class NamingCoverage(PlatformProfile profile, RegionNamer namer, ICaptureSource captures)
{
    /// <summary>
    /// Names every live block at each captured cutoff of <paramref name="recording"/>, in recording order.
    /// </summary>
    /// <param name="recording">A recording replay validation accepted, so its replay holds the recorded addresses.</param>
    /// <returns>One entry per load with a cutoff capture.</returns>
    public IReadOnlyList<LoadNaming> Measure(Recording recording)
    {
        ArgumentNullException.ThrowIfNull(recording);
        return
        [
            .. from segment in recording.Segments
               from load in segment.Loads
               where load.Heap.Cutoff is { CaptureId: not null }
               select Measure(segment.Index, load, captures.Find(recording.Id, load.Heap.Cutoff!.Value.CaptureId!))
        ];
    }

    private LoadNaming Measure(int segment, RecordedLoad load, ILoadCapture? capture)
    {
        BlockTracker tracker = new(profile.Heap0);
        HeapReplayer replayer = new(profile, load.Heap.Start.ToHeap(profile.Heap0));
        tracker.BeginLoad();

        for (int op = 0; op < load.Heap.Cutoff!.Value.RequestCount; op++)
            tracker.Apply(replayer, op, load.Heap.Requests[op]);

        return new LoadNaming(segment, load, [.. tracker.Live.Select(block => Measure(block, capture))]);
    }

    private BlockNaming Measure(PlacedBlock block, ILoadCapture? capture)
    {
        RegionName NameAt(uint offset) => namer.Name(new LandingRegion(RegionKind.Block, block, offset), capture)!;

        Dictionary<NamingDepth, uint> bytes = [];
        for (uint offset = 0; offset < block.Size; offset += sizeof(uint))
        {
            NamingDepth depth = NameAt(offset).Depth;
            bytes[depth] = bytes.GetValueOrDefault(depth) + Math.Min(sizeof(uint), block.Size - offset);
        }

        return new BlockNaming(block, NameAt(0), bytes);
    }
}
