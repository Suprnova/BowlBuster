using BowlBuster.Memory;
using BowlBuster.Platforms;

namespace BowlBuster.Tests.Memory;

public class ModelPoolTests
{
    private const uint LargePoolBlock = 0x6F6F50;
    private const uint MediumPoolBlock = 0x729E10;
    private const uint SmallPoolBlock = 0x736070;

    private const uint LargePoolFirstInstance = 0x727F5C;
    private const uint MediumPoolFirstInstance = 0x73321C;
    private const uint SmallPoolFirstInstance = 0x73B17C;

    private const uint LargePoolSize = 208_556;
    private const uint MediumPoolSize = 49_740;
    private const uint SmallPoolSize = 72_588;

    private const int LargePoolCount = 49;
    private const int MediumPoolCount = 74;
    private const int SmallPoolCount = 324;

    private const uint InstanceStride = 0xA0;

    private static readonly ModelPoolProfile Profile = PlatformProfile.XboxNtscU.Pools;

    private readonly ModelPools pools;

    public ModelPoolTests()
    {
        pools = new ModelPools(Profile);
        pools.TryAdd(LargePoolSize, LargePoolBlock, LargePoolBlock);
        pools.TryAdd(MediumPoolSize, MediumPoolBlock, MediumPoolBlock);
        pools.TryAdd(SmallPoolSize, SmallPoolBlock, SmallPoolBlock);
    }

    private static uint BlockOfSize(uint size) => size switch
    {
        LargePoolSize => LargePoolBlock,
        MediumPoolSize => MediumPoolBlock,
        _ => SmallPoolBlock,
    };

    private void AllocateMany(int count, int matrices)
    {
        for (int instance = 0; instance < count; instance++)
        {
            pools.Allocate(matrices);
        }
    }

    [Theory]
    [InlineData(0x31, 0x40, LargePoolSize)]
    [InlineData(0x4A, 8, MediumPoolSize)]
    [InlineData(0x144, 1, SmallPoolSize)]
    public void BlockSize_EachShape_MatchesTheGamesBlock(int count, int matrices, uint expected) =>
        Assert.Equal(expected, Profile.BlockSize(new ModelPoolShape(count, matrices)));

    [Fact]
    public void Shapes_Xbox_AreTheThreeShapesInCreationOrder() =>
        Assert.Equal([new(0x31, 0x40), new(0x4A, 8), new(0x144, 1)], Profile.Shapes);

    [Theory]
    [InlineData(0, 0u, 1)]
    [InlineData(5, 0u, 6)]
    [InlineData(5, 0x40u, 7)]
    [InlineData(0, 0x40u, 2)]
    [InlineData(5, 0x3Fu, 6)]
    public void MatricesFor_NodesAndFlags_CountsOnePerNodeOneMoreAndTheFlag(int nodeCount, uint flags, int expected) =>
        Assert.Equal(expected, Profile.MatricesFor(nodeCount, flags));

    [Fact]
    public void Allocate_OneMatrix_ReturnsInstancesInAddressOrder()
    {
        uint first = pools.Allocate(1);
        uint second = pools.Allocate(1);

        Assert.Equal(0x73B17Cu, first);
        Assert.Equal(0x73B21Cu, second);
    }

    [Theory]
    [InlineData(1, SmallPoolFirstInstance)]
    [InlineData(2, MediumPoolFirstInstance)]
    [InlineData(8, MediumPoolFirstInstance)]
    [InlineData(9, LargePoolFirstInstance)]
    [InlineData(64, LargePoolFirstInstance)]
    [InlineData(65, 0u)]
    public void Allocate_ByMatrixCount_TakesTheSmallestPoolThatFits(int matrices, uint expected) =>
        Assert.Equal(expected, pools.Allocate(matrices));

    [Theory]
    [InlineData(LargePoolSize, MediumPoolSize, SmallPoolSize)]
    [InlineData(LargePoolSize, SmallPoolSize, MediumPoolSize)]
    [InlineData(MediumPoolSize, LargePoolSize, SmallPoolSize)]
    [InlineData(MediumPoolSize, SmallPoolSize, LargePoolSize)]
    [InlineData(SmallPoolSize, LargePoolSize, MediumPoolSize)]
    [InlineData(SmallPoolSize, MediumPoolSize, LargePoolSize)]
    public void Allocate_AnyCreationOrder_SelectsTheSamePools(uint first, uint second, uint third)
    {
        ModelPools reordered = new(Profile);
        foreach (uint size in new[] { first, second, third })
        {
            reordered.TryAdd(size, BlockOfSize(size), BlockOfSize(size));
        }

        uint[] instances = [reordered.Allocate(1), reordered.Allocate(8), reordered.Allocate(64)];

        Assert.Equal([SmallPoolFirstInstance, MediumPoolFirstInstance, LargePoolFirstInstance], instances);
    }

    [Fact]
    public void Allocate_SmallestPoolExhausted_FallsBackToTheNextLarger()
    {
        AllocateMany(SmallPoolCount, 1);

        uint instance = pools.Allocate(1);

        Assert.Equal(MediumPoolFirstInstance, instance);
    }

    [Fact]
    public void Allocate_TwoPoolsExhausted_FallsBackToTheLargest()
    {
        AllocateMany(SmallPoolCount + MediumPoolCount, 1);

        uint instance = pools.Allocate(1);

        Assert.Equal(LargePoolFirstInstance, instance);
    }

    [Fact]
    public void Allocate_EveryPoolExhausted_ReturnsZero()
    {
        AllocateMany(SmallPoolCount + MediumPoolCount + LargePoolCount, 1);

        uint instance = pools.Allocate(1);

        Assert.Equal(0u, instance);
    }

    [Fact]
    public void Allocate_NoPools_ReturnsZero() => Assert.Equal(0u, new ModelPools(Profile).Allocate(1));

    [Fact]
    public void Free_TwoInstances_LastFreedComesBackFirstThenTheListContinues()
    {
        uint first = pools.Allocate(1);
        uint second = pools.Allocate(1);
        uint third = pools.Allocate(1);

        pools.Free(second);
        pools.Free(first);
        uint[] taken = [pools.Allocate(1), pools.Allocate(1), pools.Allocate(1)];

        Assert.Equal([first, second, third + InstanceStride], taken);
    }

    [Fact]
    public void Free_SameInstanceTwice_ComesBackTwice()
    {
        uint instance = pools.Allocate(1);

        pools.Free(instance);
        pools.Free(instance);
        uint[] taken = [pools.Allocate(1), pools.Allocate(1)];

        Assert.Equal([instance, instance], taken);
    }

    [Theory]
    [InlineData(0x100000u)]
    [InlineData(SmallPoolFirstInstance + 4)]
    [InlineData(SmallPoolFirstInstance - InstanceStride)]
    [InlineData(SmallPoolFirstInstance + (InstanceStride * SmallPoolCount))]
    public void Free_AddressThatIsNoInstance_ChangesNothing(uint address)
    {
        pools.Free(address);

        uint instance = pools.Allocate(1);

        Assert.Equal(SmallPoolFirstInstance, instance);
    }

    [Fact]
    public void Free_PoolAtAnotherAddressThanRecorded_ReadsTheRecordedAddressAndReturnsTheSimulatedOne()
    {
        const uint simulatedBlock = 0x736330;
        ModelPools shifted = new(Profile);
        shifted.TryAdd(SmallPoolSize, simulatedBlock, SmallPoolBlock);
        shifted.Allocate(1);
        shifted.Allocate(1);

        shifted.Free(SmallPoolFirstInstance);
        uint instance = shifted.Allocate(1);

        Assert.Equal(0x73B43Cu, instance);
    }

    [Theory]
    [InlineData(0u)]
    [InlineData(SmallPoolSize + 1)]
    [InlineData(0x1000u)]
    public void TryAdd_SizeNoShapeHas_ReturnsFalseAndAddsNoPool(uint size)
    {
        ModelPools empty = new(Profile);

        bool added = empty.TryAdd(size, SmallPoolBlock, SmallPoolBlock);

        Assert.False(added);
        Assert.Equal(0u, empty.Allocate(1));
    }

    [Fact]
    public void FreeCount_NewPool_IsEveryInstance()
    {
        ModelPool pool = new(Profile, new ModelPoolShape(SmallPoolCount, 1), SmallPoolBlock, SmallPoolBlock);

        Assert.Equal(SmallPoolCount, pool.FreeCount);
    }

    [Fact]
    public void Take_EmptyPool_Throws()
    {
        ModelPool pool = new(Profile, new ModelPoolShape(1, 1), SmallPoolBlock, SmallPoolBlock);
        pool.Take();

        Assert.Throws<InvalidOperationException>(() => pool.Take());
    }

    [Theory]
    [InlineData(SmallPoolFirstInstance, true)]
    [InlineData(SmallPoolFirstInstance + 4, false)]
    public void TryFree_InstanceOrNot_SaysWhetherItFreed(uint address, bool expected)
    {
        ModelPool pool = new(Profile, new ModelPoolShape(SmallPoolCount, 1), SmallPoolBlock, SmallPoolBlock);
        pool.Take();

        bool freed = pool.TryFree(address);

        Assert.Equal(expected, freed);
        Assert.Equal(expected ? SmallPoolCount : SmallPoolCount - 1, pool.FreeCount);
    }
}
