using BowlBuster.Platforms;

namespace BowlBuster.Landings;

/// <summary>
/// Names a model pool: every instance's matrices, then the header, then the instances.
/// </summary>
/// <param name="pools">The model pools' constants.</param>
internal sealed class ModelPoolNamer(ModelPoolProfile pools) : IBlockNamer
{
    public RegionName? Name(PlacedBlock block, uint offset, NamingContext context)
    {
        if (pools.ShapeOfSize(block.Size) is not { } shape) return null;

        uint matrixBytes = pools.MatrixBytes(shape);
        if (offset < matrixBytes)
        {
            uint perInstance = (uint)shape.Matrices * pools.MatrixSize;
            uint inInstance = offset % perInstance;
            return new ModelMatrixName(shape, (int)(offset / perInstance), (int)(inInstance / pools.MatrixSize), inInstance % pools.MatrixSize);
        }

        uint pastMatrices = offset - matrixBytes;
        if (pastMatrices < pools.HeaderSize) return new ModelPoolHeaderName(shape, pastMatrices, pools.HeaderFields.FieldAt(pastMatrices));

        uint pastHeader = pastMatrices - pools.HeaderSize;
        uint inInstanceRecord = pastHeader % pools.InstanceSize;
        return new ModelInstanceName(shape, (int)(pastHeader / pools.InstanceSize), inInstanceRecord, pools.InstanceFields.FieldAt(inInstanceRecord));
    }
}

/// <summary>
/// Names a model instance allocated outside the pools: its matrices, then the instance.
/// </summary>
/// <param name="pools">The model pools' constants, which give the instance's and a matrix's sizes.</param>
internal sealed class ModelInstanceNamer(ModelPoolProfile pools) : IBlockNamer
{
    public RegionName? Name(PlacedBlock block, uint offset, NamingContext context)
    {
        if (block.Size < pools.InstanceSize || (block.Size - pools.InstanceSize) % pools.MatrixSize is not 0) return null;

        uint matrixBytes = block.Size - pools.InstanceSize;
        return offset < matrixBytes
            ? new ModelMatrixName(null, 0, (int)(offset / pools.MatrixSize), offset % pools.MatrixSize)
            : new ModelInstanceName(null, 0, offset - matrixBytes, pools.InstanceFields.FieldAt(offset - matrixBytes));
    }
}
