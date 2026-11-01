namespace BowlBuster.Platforms;

/// <summary>
/// The constants of the model pools on one platform.
/// </summary>
/// <remarks>
/// A pool is one heap block: the matrices of every instance, then a header, then the instances.
/// </remarks>
/// <param name="Shapes">The pools a scene creates, in creation order.</param>
/// <param name="HeaderSize">The size in bytes of a pool's header.</param>
/// <param name="InstanceSize">The size in bytes of one model instance.</param>
/// <param name="MatrixSize">The size in bytes of one bone matrix.</param>
/// <param name="ExtraMatrixFlag">The model flag bit that makes an instance need one more matrix.</param>
public sealed record ModelPoolProfile(
    IReadOnlyList<ModelPoolShape> Shapes,
    uint HeaderSize,
    uint InstanceSize,
    uint MatrixSize,
    uint ExtraMatrixFlag)
{
    /// <summary>
    /// The size of the heap block a pool occupies.
    /// </summary>
    /// <param name="shape">The pool's shape.</param>
    /// <returns>The block's size in bytes. Pools are recognised by this size, which differs for every shape.</returns>
    public uint BlockSize(ModelPoolShape shape) => ((uint)shape.Count * (((uint)shape.Matrices * MatrixSize) + InstanceSize)) + HeaderSize;

    /// <summary>
    /// The size of the matrices at the start of a pool's block.
    /// </summary>
    /// <param name="shape">The pool's shape.</param>
    /// <returns>The size in bytes. The pool's header follows them.</returns>
    public uint MatrixBytes(ModelPoolShape shape) => (uint)shape.Count * (uint)shape.Matrices * MatrixSize;

    /// <summary>
    /// Recognises a pool by its block's size.
    /// </summary>
    /// <param name="size">The block's size in bytes.</param>
    /// <returns>The pool's shape, or <see langword="null"/> when no pool has that size.</returns>
    public ModelPoolShape? ShapeOfSize(uint size) => Shapes
        .Where(shape => BlockSize(shape) == size)
        .Select(static shape => (ModelPoolShape?)shape)
        .FirstOrDefault();

    /// <summary>
    /// The number of matrices a model's instance needs.
    /// </summary>
    /// <param name="nodeCount">The number of nodes in the model's skeleton, 0 when it has none.</param>
    /// <param name="flags">The model's flags.</param>
    /// <returns>One matrix per node and one more, plus one when <paramref name="flags"/> has <see cref="ExtraMatrixFlag"/>.</returns>
    public int MatricesFor(int nodeCount, uint flags) => nodeCount + 1 + ((flags & ExtraMatrixFlag) is 0 ? 0 : 1);
}
