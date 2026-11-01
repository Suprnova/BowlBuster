using BowlBuster.Memory;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Replay;
using System.Diagnostics;

namespace BowlBuster.Landings;

/// <summary>
/// Follows the blocks of a replay across loads, so an address can be resolved against the heap as it stands.
/// </summary>
/// <remarks>
/// The allocator only keeps a cursor, so a block's extent has to be remembered as it is placed. Live blocks are held in
/// address order, which the allocator gives by only ever moving up from the cursor. A pop ends every block at or above
/// the restored cursor, and those are kept per load, because a later load's write can fall on memory an earlier load's
/// block last covered.
/// </remarks>
/// <param name="profile">The heap's constants.</param>
public sealed class BlockTracker(HeapProfile profile)
{
    private readonly List<PlacedBlock> live = [];
    private readonly List<PlacedBlock> popped = [];
    private readonly List<PlacedBlock[]> earlierLoads = [];

    private int position = -1;
    private int lastBlock = -1;

    /// <summary>
    /// The highest end of anything allocated in this load so far. Past it, the load has never used the memory.
    /// </summary>
    public uint HeapTop { get; private set; }

    /// <summary>
    /// Starts the chain's next load.
    /// </summary>
    public void BeginLoad()
    {
        if (position >= 0) earlierLoads.Add([.. popped.OrderBy(static block => block.Address)]);

        popped.Clear();
        position++;
        HeapTop = live.Count > 0 ? live[^1].End : 0;
    }

    /// <summary>
    /// Applies a request and follows what it does to the blocks. A zero-size or failed allocation places no block.
    /// </summary>
    /// <param name="replayer">The load's replayer.</param>
    /// <param name="op">The request's position in the load.</param>
    /// <param name="request">The request.</param>
    /// <returns>What <see cref="HeapReplayer.Apply"/> returned.</returns>
    public uint? Apply(HeapReplayer replayer, int op, HeapRequest request)
    {
        ArgumentNullException.ThrowIfNull(replayer);

        uint cursor = replayer.Heap.Current.Cursor;
        uint? result = replayer.Apply(request);

        switch (request)
        {
            case AllocRequest { Size: not 0 } alloc when result is { } address and not 0:
                Place(new PlacedBlock(position, op, cursor, address, alloc.Size, alloc));
                break;

            case GrowRequest when result is not 0 && lastBlock >= 0:
                Resize(replayer.Heap.LastBlock!.Value.Size);
                break;

            case PopRequest:
                EndBlocksAbove(replayer.Heap.Current.Cursor);
                break;
        }

        return result;
    }

    /// <summary>
    /// Pops to a depth outside the recorded requests, as a scene's exit does.
    /// </summary>
    /// <param name="heap">The heap.</param>
    /// <param name="depth">The depth to return to.</param>
    public void PopTo(GameHeap heap, int depth)
    {
        ArgumentNullException.ThrowIfNull(heap);

        heap.Pop(depth);
        EndBlocksAbove(heap.Current.Cursor);
    }

    /// <summary>
    /// Finds the block a request of this load placed, live or popped.
    /// </summary>
    /// <param name="op">The request's position in the load.</param>
    /// <returns>The block, or <see langword="null"/> when that request placed none.</returns>
    public PlacedBlock? Find(int op) => FirstOfThisLoad(block => block.Op == op);

    /// <summary>
    /// Finds the first block of this load allocated from a site, live or popped.
    /// </summary>
    /// <param name="caller">The allocation's return address.</param>
    /// <returns>The block, or <see langword="null"/> when the load has none from that site.</returns>
    public PlacedBlock? FindFrom(uint caller) => FirstOfThisLoad(block => block.Request.Caller == caller);

    /// <summary>
    /// Says what lies at an address now.
    /// </summary>
    /// <param name="address">The address.</param>
    /// <param name="originPosition">The position of the load that set the sphere. Blocks of that load and earlier never count as having last covered an address above the heap.</param>
    /// <returns>The region.</returns>
    /// <exception cref="UnreachableException">The address is below every tracked block, which a sphere from the replay can't be.</exception>
    public LandingRegion Locate(uint address, int originPosition)
    {
        int index = LastAtOrBelow(live, address);

        if (index < 0) throw new UnreachableException($"0x{address:X} is below every tracked block.");

        if (address < live[index].End) return new LandingRegion(RegionKind.Block, live[index], address - live[index].Address);

        if (index + 1 < live.Count) return Between(live[index + 1], address);

        return address < HeapTop ? Freed(address) : AboveHeap(address, originPosition);
    }

    private static int LastAtOrBelow(IReadOnlyList<PlacedBlock> blocks, uint address)
    {
        int low = 0;
        int high = blocks.Count - 1;

        while (low <= high)
        {
            int middle = low + ((high - low) / 2);

            if (blocks[middle].Address <= address) low = middle + 1;
            else high = middle - 1;
        }

        return high;
    }

    private PlacedBlock? FirstOfThisLoad(Func<PlacedBlock, bool> match) => live
        .Concat(popped)
        .Where(block => block.Position == position && match(block))
        .Select(static block => (PlacedBlock?)block)
        .FirstOrDefault();

    private void Place(PlacedBlock block)
    {
        live.Add(block);
        lastBlock = live.Count - 1;
        HeapTop = Math.Max(HeapTop, block.End);
    }

    private void Resize(uint size)
    {
        live[lastBlock] = live[lastBlock] with { Size = size };
        HeapTop = Math.Max(HeapTop, live[lastBlock].End);
    }

    private void EndBlocksAbove(uint cursor)
    {
        int firstEnded = LastAtOrBelow(live, cursor - 1) + 1;

        popped.AddRange(live.Skip(firstEnded));
        live.RemoveRange(firstEnded, live.Count - firstEnded);

        if (lastBlock >= live.Count) lastBlock = -1;
    }

    private LandingRegion Between(PlacedBlock next, uint address)
    {
        uint intoHeader = address - next.Header;

        return address >= next.Header && intoHeader < profile.HeaderAllowance
            ? new LandingRegion(RegionKind.Header, next, intoHeader)
            : new LandingRegion(RegionKind.Padding, next, next.Address - address);
    }

    private LandingRegion Freed(uint address)
    {
        PlacedBlock? holder = popped
            .Where(block => address >= block.Address && address < block.End)
            .Select(static block => (PlacedBlock?)block)
            .LastOrDefault();

        return new LandingRegion(RegionKind.Freed, holder, holder is { } block ? address - block.Address : 0);
    }

    private LandingRegion AboveHeap(uint address, int originPosition)
    {
        for (int load = position - 1; load > originPosition; load--)
        {
            int index = LastAtOrBelow(earlierLoads[load], address);

            if (index >= 0 && address < earlierLoads[load][index].End)
                return new LandingRegion(RegionKind.AboveHeap, earlierLoads[load][index], address - earlierLoads[load][index].Address);
        }

        return new LandingRegion(RegionKind.AboveHeap, null, 0);
    }
}
