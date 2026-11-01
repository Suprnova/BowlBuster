namespace BowlBuster.Memory;

/// <summary>
/// A field in which two views of the heap disagree.
/// </summary>
/// <param name="Field">The field, such as <c>depth</c>, <c>states[2].cursor</c> or <c>last_block.size</c>.</param>
/// <param name="Value">The field in the first view, or <see langword="null"/> when that view has no last block.</param>
/// <param name="OtherValue">The field in the other view, or <see langword="null"/> when that view has no last block.</param>
public readonly record struct HeapDifference(string Field, uint? Value, uint? OtherValue);
