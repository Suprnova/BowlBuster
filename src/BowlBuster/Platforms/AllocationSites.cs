namespace BowlBuster.Platforms;

/// <summary>
/// The return addresses of the allocations the simulator tells apart. A recorded allocation's caller is compared with
/// these to learn what it allocated.
/// </summary>
/// <param name="PlayerEntity">The player entity that every scene load allocates and never frees.</param>
/// <param name="ModelPool">A model pool's block.</param>
/// <param name="Sphere">The Macho Bowl's sphere, a model instance taken from a pool when SpongeBob's character initialises.</param>
/// <param name="ArchiveLayer">An archive layer that lives in the heap, or an asset directory, which comes from the same site.</param>
/// <param name="ModelInstance">A model instance allocated straight from the heap, outside the pools.</param>
public sealed record AllocationSites(uint PlayerEntity, uint ModelPool, uint Sphere, uint ArchiveLayer, uint ModelInstance);
