using BowlBuster.Platforms;

namespace BowlBuster.Memory;

/// <summary>
/// A <see cref="GameHeap"/>'s state at one moment: what the game's heap descriptor holds, apart from its constants.
/// </summary>
/// <param name="States">The depth states from depth 0 up to the current depth, which is the last one.</param>
/// <param name="LastBlock">The block most recently allocated or grown, if any.</param>
public sealed record HeapSnapshot(IReadOnlyList<HeapState> States, HeapBlock? LastBlock)
{
    /// <summary>
    /// The current depth.
    /// </summary>
    public int Depth => States.Count - 1;

    /// <summary>
    /// Takes a snapshot of a heap, which later requests on the heap don't change.
    /// </summary>
    /// <param name="heap">The heap.</param>
    /// <returns>The heap's state.</returns>
    public static HeapSnapshot Of(GameHeap heap)
    {
        ArgumentNullException.ThrowIfNull(heap);
        return new HeapSnapshot([.. heap.States], heap.LastBlock);
    }

    /// <summary>
    /// Creates a heap in this state.
    /// </summary>
    /// <param name="profile">The heap's constants.</param>
    /// <returns>The heap.</returns>
    /// <exception cref="ArgumentException"><see cref="States"/> is empty or has more states than the heap has depths.</exception>
    public GameHeap ToHeap(HeapProfile profile) => new(profile, States, LastBlock);

    /// <summary>
    /// Compares this state with another, in the order a reader would debug them: the depth, each depth state from depth 0
    /// up, then the last block.
    /// </summary>
    /// <param name="other">The other state.</param>
    /// <returns>The first field that differs, or <see langword="null"/> when the states are equal.</returns>
    public HeapDifference? FirstDifference(HeapSnapshot other)
    {
        ArgumentNullException.ThrowIfNull(other);

        if (Depth != other.Depth) return new HeapDifference("depth", (uint)Depth, (uint)other.Depth);

        for (int depth = 0; depth < States.Count; depth++)
        {
            (HeapState state, HeapState otherState) = (States[depth], other.States[depth]);

            if (state.Cursor != otherState.Cursor)
                return new HeapDifference($"states[{depth}].cursor", state.Cursor, otherState.Cursor);

            if (state.BlockCount != otherState.BlockCount)
                return new HeapDifference($"states[{depth}].blocks", (uint)state.BlockCount, (uint)otherState.BlockCount);

            if (state.Used != otherState.Used)
                return new HeapDifference($"states[{depth}].used", state.Used, otherState.Used);
        }

        return (LastBlock, other.LastBlock) switch
        {
            (null, null) => null,
            ({ } block, null) => new HeapDifference("last_block", block.Address, null),
            (null, { } block) => new HeapDifference("last_block", null, block.Address),
            ({ } block, { } otherBlock) when block.Address != otherBlock.Address => new HeapDifference("last_block.address", block.Address, otherBlock.Address),
            ({ } block, { } otherBlock) when block.Size != otherBlock.Size => new HeapDifference("last_block.size", block.Size, otherBlock.Size),
            _ => null,
        };
    }
}
