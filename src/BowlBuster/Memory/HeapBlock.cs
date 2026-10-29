namespace BowlBuster.Memory;

/// <summary>
/// A block allocated from a <see cref="GameHeap"/>.
/// </summary>
/// <param name="Address">The address of the block's first byte.</param>
/// <param name="Size">The size the block was requested with, plus every grow applied to it.</param>
public readonly record struct HeapBlock(uint Address, uint Size);
