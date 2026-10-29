namespace BowlBuster.Memory;

/// <summary>
/// One depth of a <see cref="GameHeap"/>: where the next block goes and what has been allocated so far.
/// </summary>
/// <param name="Cursor">The address the next block's header record is written at.</param>
/// <param name="BlockCount">The number of blocks allocated at this depth and the depths below it.</param>
/// <param name="Used">The bytes allocated at this depth and the depths below it, headers and padding included.</param>
public readonly record struct HeapState(uint Cursor, int BlockCount, uint Used);
