namespace BowlBuster.Platforms;

/// <summary>
/// The constants of one game heap on one platform.
/// </summary>
/// <param name="Size">The heap's capacity in bytes. An allocation fails when the bytes already used plus its advance would pass it.</param>
/// <param name="HeaderAllowance">The bytes the allocator reserves ahead of every block for the block's header record.</param>
/// <param name="DefaultAlignment">The alignment, a power of two, that every block is raised to when it asks for less.</param>
/// <param name="DepthCount">The number of depth states the heap keeps, which bounds how many times it can be pushed.</param>
public sealed record HeapProfile(uint Size, uint HeaderAllowance, uint DefaultAlignment, int DepthCount);
