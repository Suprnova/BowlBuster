using BowlBuster.Platforms;
using System.Numerics;

namespace BowlBuster.Memory;

/// <summary>
/// The game's allocator for one heap, reproduced request by request so that every returned address and every depth
/// state matches the game's.
/// </summary>
/// <remarks>
/// The heap grows upward. A block is placed after a header allowance, aligned, and the cursor then moves to the next
/// multiple of 4 past the block's end. Only the layout is modelled: block contents are not.
/// </remarks>
public sealed class GameHeap
{
    /// <summary>
    /// The address the game returns for a request of size 0, which allocates nothing.
    /// </summary>
    public const uint ZeroSizeAddress = 0xDEADBEEF;

    private readonly HeapProfile profile;
    private readonly List<HeapState> states;

    /// <summary>
    /// Creates a heap in a captured state.
    /// </summary>
    /// <param name="profile">The heap's constants.</param>
    /// <param name="states">The depth states from depth 0 up to the current depth, which is the last one.</param>
    /// <param name="lastBlock">The block most recently allocated or grown, if any.</param>
    /// <exception cref="ArgumentException"><paramref name="states"/> is empty or has more states than the heap has depths.</exception>
    public GameHeap(HeapProfile profile, IEnumerable<HeapState> states, HeapBlock? lastBlock = null)
    {
        ArgumentNullException.ThrowIfNull(profile);
        ArgumentNullException.ThrowIfNull(states);

        this.profile = profile;
        this.states = [.. states];
        LastBlock = lastBlock;

        if (this.states.Count < 1 || this.states.Count > profile.DepthCount)
            throw new ArgumentException($"A heap has between 1 and {profile.DepthCount} depth states.", nameof(states));
    }

    /// <summary>
    /// The current depth: the index of <see cref="Current"/> in <see cref="States"/>.
    /// </summary>
    public int Depth => states.Count - 1;

    /// <summary>
    /// The state allocations are made in.
    /// </summary>
    public HeapState Current => states[^1];

    /// <summary>
    /// The depth states from depth 0 up to the current depth.
    /// </summary>
    public IReadOnlyList<HeapState> States => states;

    /// <summary>
    /// The block most recently allocated or grown, or <see langword="null"/> when there is none. The heap owns it, not a
    /// depth, so popping does not change it.
    /// </summary>
    public HeapBlock? LastBlock { get; private set; }

    /// <summary>
    /// Allocates a block in the current state.
    /// </summary>
    /// <param name="size">The size in bytes.</param>
    /// <param name="alignment">The alignment in bytes, a power of two. A value below the heap's default is raised to it, so 0 means the default.</param>
    /// <returns>
    /// The block's address; <see cref="ZeroSizeAddress"/> when <paramref name="size"/> is 0; or 0 when the bytes used plus
    /// the allocation's advance would pass the heap's size. In the last two cases the heap is unchanged.
    /// </returns>
    /// <exception cref="ArgumentOutOfRangeException">The effective alignment is not a power of two.</exception>
    public uint Allocate(uint size, uint alignment)
    {
        alignment = Math.Max(alignment, profile.DefaultAlignment);

        if (!BitOperations.IsPow2(alignment))
            throw new ArgumentOutOfRangeException(nameof(alignment), alignment, "The alignment must be a power of two.");

        if (size is 0) return ZeroSizeAddress;

        HeapState current = Current;
        uint misalignment = (current.Cursor + profile.HeaderAllowance) & (alignment - 1);
        uint padding = misalignment is 0 ? 0 : alignment - misalignment;
        uint address = current.Cursor + profile.HeaderAllowance + padding;
        uint advance = (profile.HeaderAllowance + padding + size + 3) & ~3u;

        if (current.Used + (ulong)advance > profile.Size) return 0;

        states[^1] = new HeapState(current.Cursor + advance, current.BlockCount + 1, current.Used + advance);
        LastBlock = new HeapBlock(address, size);
        return address;
    }
}
