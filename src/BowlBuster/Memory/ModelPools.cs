using BowlBuster.Platforms;

namespace BowlBuster.Memory;

/// <summary>
/// The model pools of one load, which the scene creates as it starts and which last until the next scene's.
/// </summary>
/// <remarks>
/// The list is kept sorted by matrix count, descending, and an allocation takes the last pool in it with a free instance
/// and enough matrices: the smallest pool that fits, falling back to a larger one when that pool is exhausted.
/// </remarks>
/// <param name="profile">The model pools' constants.</param>
public sealed class ModelPools(ModelPoolProfile profile)
{
    private readonly ModelPoolProfile profile = profile ?? throw new ArgumentNullException(nameof(profile));
    private readonly List<ModelPool> pools = [];

    /// <summary>
    /// Adds a pool for a heap block, when the block's size is a pool's.
    /// </summary>
    /// <param name="size">The block's size in bytes.</param>
    /// <param name="address">The block in the simulated heap.</param>
    /// <param name="recordedAddress">The block in the recording's run.</param>
    /// <returns><see langword="true"/> when a pool was added; <see langword="false"/> when no shape has this size.</returns>
    public bool TryAdd(uint size, uint address, uint recordedAddress)
    {
        foreach (ModelPoolShape shape in profile.Shapes)
        {
            if (profile.BlockSize(shape) != size) continue;

            int next = pools.FindIndex(pool => pool.Shape.Matrices < shape.Matrices);
            pools.Insert(next < 0 ? pools.Count : next, new ModelPool(profile, shape, address, recordedAddress));
            return true;
        }

        return false;
    }

    /// <summary>
    /// Takes an instance from the smallest pool that can serve it.
    /// </summary>
    /// <param name="matrices">The number of matrices the instance needs.</param>
    /// <returns>The instance's simulated address, or 0 when no pool has a free instance with enough matrices.</returns>
    public uint Allocate(int matrices) =>
        pools.FindLast(pool => pool.FreeCount > 0 && pool.Shape.Matrices >= matrices)?.Take() ?? 0;

    /// <summary>
    /// Frees an instance. An address in no current pool is ignored, as the game ignores an instance that didn't come from
    /// a pool.
    /// </summary>
    /// <param name="recordedInstance">The instance's address in the recording's run.</param>
    public void Free(uint recordedInstance) => pools.Exists(pool => pool.TryFree(recordedInstance));
}
