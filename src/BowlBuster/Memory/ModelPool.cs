using BowlBuster.Platforms;

namespace BowlBuster.Memory;

/// <summary>
/// One model pool: a fixed set of model instances handed out through a free list.
/// </summary>
/// <remarks>
/// The free list starts at instance 0 in address order, and a freed instance goes back on top, so the next allocation
/// gets it back. Freeing never checks that the instance is in use, so a double free puts it on the list twice, as the
/// game's list does.
/// <para>
/// A pool has two addresses. Instances are handed out at its simulated address, which is where the replayed heap put its
/// block. Frees arrive as recorded, so they are read against the address the recording's run put the block at.
/// </para>
/// </remarks>
public sealed class ModelPool
{
    private readonly uint instanceSize;
    private readonly uint firstInstance;
    private readonly uint firstRecordedInstance;
    private readonly Stack<int> free;

    /// <summary>
    /// Creates a pool with every instance free.
    /// </summary>
    /// <param name="profile">The model pools' constants.</param>
    /// <param name="shape">The pool's shape.</param>
    /// <param name="address">The pool's block in the simulated heap.</param>
    /// <param name="recordedAddress">The pool's block in the recording's run.</param>
    public ModelPool(ModelPoolProfile profile, ModelPoolShape shape, uint address, uint recordedAddress)
    {
        ArgumentNullException.ThrowIfNull(profile);

        uint instancesOffset = profile.MatrixBytes(shape) + profile.HeaderSize;

        Shape = shape;
        instanceSize = profile.InstanceSize;
        firstInstance = address + instancesOffset;
        firstRecordedInstance = recordedAddress + instancesOffset;
        free = new Stack<int>(Enumerable.Range(0, shape.Count).Reverse());
    }

    /// <summary>
    /// The pool's shape.
    /// </summary>
    public ModelPoolShape Shape { get; }

    /// <summary>
    /// The number of instances on the free list.
    /// </summary>
    public int FreeCount => free.Count;

    /// <summary>
    /// Takes the instance at the head of the free list.
    /// </summary>
    /// <returns>The instance's simulated address.</returns>
    /// <exception cref="InvalidOperationException">The free list is empty.</exception>
    public uint Take() => firstInstance + ((uint)free.Pop() * instanceSize);

    /// <summary>
    /// Puts an instance back on top of the free list.
    /// </summary>
    /// <param name="recordedInstance">The instance's address in the recording's run.</param>
    /// <returns><see langword="true"/> when the address is one of this pool's instances; otherwise the pool is unchanged.</returns>
    public bool TryFree(uint recordedInstance)
    {
        if (recordedInstance < firstRecordedInstance) return false;

        uint offset = recordedInstance - firstRecordedInstance;
        if (offset % instanceSize is not 0 || offset / instanceSize >= (uint)Shape.Count) return false;

        free.Push((int)(offset / instanceSize));
        return true;
    }
}
