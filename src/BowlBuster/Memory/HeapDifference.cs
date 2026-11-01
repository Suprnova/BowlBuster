namespace BowlBuster.Memory;

/// <summary>
/// The first field in which two <see cref="HeapSnapshot"/>s disagree.
/// </summary>
/// <param name="Field">The field, such as <c>depth</c>, <c>states[2].cursor</c> or <c>last_block.size</c>.</param>
/// <param name="Value">The field in the snapshot that was asked, or <see langword="null"/> when it has no last block.</param>
/// <param name="OtherValue">The field in the other snapshot, or <see langword="null"/> when it has no last block.</param>
public readonly record struct HeapDifference(string Field, uint? Value, uint? OtherValue);
