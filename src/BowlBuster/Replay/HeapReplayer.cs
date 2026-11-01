using BowlBuster.Memory;
using BowlBuster.Platforms;
using BowlBuster.Recordings;

namespace BowlBuster.Replay;

/// <summary>
/// Runs one load's recorded requests through the allocator and the model pools, on a heap in any state.
/// </summary>
/// <remarks>
/// The results are the replay's own: a heap shifted from the recording's run gets different addresses from the ones in
/// the requests. A replayer lasts one load, because a scene starts with no model pools of its own.
/// </remarks>
/// <param name="profile">The platform's constants.</param>
/// <param name="heap">The heap to replay on.</param>
public sealed class HeapReplayer(PlatformProfile profile, GameHeap heap)
{
    private readonly PlatformProfile profile = profile ?? throw new ArgumentNullException(nameof(profile));
    private readonly ModelPools pools = new(profile.Pools);

    /// <summary>
    /// The heap being replayed on.
    /// </summary>
    public GameHeap Heap { get; } = heap ?? throw new ArgumentNullException(nameof(heap));

    /// <summary>
    /// Applies one request.
    /// </summary>
    /// <param name="request">The request.</param>
    /// <returns>
    /// What the game would return: the address for an allocation, a grow or a pool allocation, with 0 when it fails, or
    /// <see langword="null"/> for a push, a pop or a free.
    /// </returns>
    /// <exception cref="ArgumentException"><paramref name="request"/> is of an unknown type.</exception>
    /// <exception cref="ArgumentOutOfRangeException">The request has an alignment the game never uses, or pops above the current depth.</exception>
    /// <exception cref="InvalidOperationException">The request grows with no last block, or pushes past the heap's depths.</exception>
    public uint? Apply(HeapRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        switch (request)
        {
            case AllocRequest alloc:
                return Allocate(alloc);

            case GrowRequest grow:
                return Heap.Grow(grow.Size);

            case PoolAllocRequest instance:
                return pools.Allocate(profile.Pools.MatricesFor(instance.NodeCount, instance.Flags));

            case PushRequest:
                Heap.Push();
                return null;

            case PopRequest pop:
                Heap.Pop(pop.Depth);
                return null;

            case PoolFreeRequest free:
                pools.Free(free.Instance);
                return null;

            default:
                throw new ArgumentException($"Unknown request type {request.GetType().Name}.", nameof(request));
        }
    }

    private uint Allocate(AllocRequest request)
    {
        uint address = Heap.Allocate(request.Size, request.Alignment);

        if (request.Caller == profile.Sites.ModelPool && address is not 0)
            pools.TryAdd(request.Size, address, request.Address);

        return address;
    }
}
