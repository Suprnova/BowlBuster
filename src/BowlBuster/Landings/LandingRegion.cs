using BowlBuster.Recordings;

namespace BowlBuster.Landings;

/// <summary>
/// What lies at an address in the heap at a load's cutoff.
/// </summary>
/// <param name="Kind">The kind of memory.</param>
/// <param name="Block">The block the kind refers to, or <see langword="null"/> when it has none.</param>
/// <param name="Offset">Where the address falls. What it counts from depends on <paramref name="Kind"/>.</param>
public readonly record struct LandingRegion(RegionKind Kind, PlacedBlock? Block, uint Offset);

/// <summary>
/// The kinds of memory an address can fall in at a load's cutoff.
/// </summary>
public enum RegionKind
{
    /// <summary>
    /// A live block: this load's, or the player entity an earlier load leaked. The offset is into the block.
    /// </summary>
    Block,

    /// <summary>
    /// The header record the game writes ahead of a block. The block is the one it describes, and the offset is into the
    /// record.
    /// </summary>
    Header,

    /// <summary>
    /// Between two blocks, past the header: alignment padding, or the rounding after a block whose size isn't a multiple
    /// of 4. The block is the next one, and the offset counts back from its address.
    /// </summary>
    Padding,

    /// <summary>
    /// Memory this load allocated and popped, which nothing has reused. The block is the one that last held it, if any,
    /// and the offset is into that block.
    /// </summary>
    Freed,

    /// <summary>
    /// Above everything this load has allocated, so no live object uses it. The block is the newest one from a load after
    /// the origin that covered the address, with the offset into it. There is none when only the origin's own sphere
    /// instance ever held it.
    /// </summary>
    AboveHeap,
}

/// <summary>
/// A block a replay placed.
/// </summary>
/// <param name="Position">The position in the chain of the load that placed it.</param>
/// <param name="Op">The request's position in that load.</param>
/// <param name="Header">The address of the block's header record, which is where the cursor stood before the allocation.</param>
/// <param name="Address">The address of the block's first byte in the replay.</param>
/// <param name="Size">The block's size, grows included.</param>
/// <param name="Request">The recorded allocation, which holds the block's address in the recording's run and what it is for.</param>
public readonly record struct PlacedBlock(int Position, int Op, uint Header, uint Address, uint Size, AllocRequest Request)
{
    /// <summary>
    /// The first address past the block.
    /// </summary>
    public uint End => Address + Size;
}
