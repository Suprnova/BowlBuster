namespace BowlBuster.Platforms;

/// <summary>
/// What the stale write touches on one platform, as offsets from the stale sphere pointer: the words it stores, and the
/// fields the render path then reads through the same pointer.
/// </summary>
/// <param name="Words">The words, those written first.</param>
public sealed record FootprintProfile(IReadOnlyList<FootprintWord> Words);

/// <summary>
/// One field the stale write stores or the render path reads.
/// </summary>
/// <param name="Offset">The offset from the stale sphere pointer.</param>
/// <param name="Size">The field's size in bytes.</param>
/// <param name="Written">The value the stale write stores here, or <see langword="null"/> for a field that is only read.</param>
public readonly record struct FootprintWord(uint Offset, int Size, uint? Written);
