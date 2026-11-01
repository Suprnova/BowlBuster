namespace BowlBuster.Recordings;

/// <summary>
/// One request the game made of heap 0 or of the model pools during a load. A load's requests, in order, are what replay
/// runs, and a request's position among them is its op, which identifies the block it made.
/// </summary>
/// <remarks>
/// Addresses in a request are the ones the recording's run saw. A replay on a shifted heap gets different ones.
/// </remarks>
public abstract record HeapRequest;

/// <summary>
/// A block allocated from the heap.
/// </summary>
/// <param name="Size">The size asked for, in bytes.</param>
/// <param name="Alignment">The alignment asked for, before the heap raises it to its default.</param>
/// <param name="Address">The address the game returned.</param>
/// <param name="Caller">The allocation's return address, which tells what the block is for.</param>
/// <param name="Layer">The archive layer the loader was loading, for an allocation from the layer allocator.</param>
public sealed record AllocRequest(uint Size, uint Alignment, uint Address, uint Caller, LayerId? Layer = null) : HeapRequest;

/// <summary>
/// The heap's last block extended in place.
/// </summary>
/// <param name="Size">The bytes asked for, before rounding.</param>
public sealed record GrowRequest(uint Size) : HeapRequest;

/// <summary>
/// A new heap depth started as a copy of the current one.
/// </summary>
public sealed record PushRequest : HeapRequest;

/// <summary>
/// The heap returned to an earlier depth, discarding everything allocated since that depth was pushed.
/// </summary>
/// <param name="Depth">The depth returned to.</param>
public sealed record PopRequest(int Depth) : HeapRequest;

/// <summary>
/// A model instance taken from a model pool. An instance the game allocates outside the pools is an
/// <see cref="AllocRequest"/> instead.
/// </summary>
/// <param name="Instance">The instance the game returned.</param>
/// <param name="Caller">The allocation's return address, which tells what the instance is for.</param>
/// <param name="NodeCount">The number of nodes in the model's skeleton, 0 when it has none.</param>
/// <param name="Flags">The model's flags.</param>
public sealed record PoolAllocRequest(uint Instance, uint Caller, int NodeCount, uint Flags) : HeapRequest;

/// <summary>
/// A model instance freed. An instance in no current pool has nothing to go back to, so the request changes nothing.
/// </summary>
/// <param name="Instance">The instance's address in the recording's run.</param>
public sealed record PoolFreeRequest(uint Instance) : HeapRequest;

/// <summary>
/// An archive layer, as the game's loader was loading it when it allocated a block.
/// </summary>
/// <param name="Archive">The archive.</param>
/// <param name="Layer">The layer's index in the archive.</param>
public readonly record struct LayerId(string Archive, int Layer);
