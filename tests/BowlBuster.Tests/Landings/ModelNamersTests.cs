using BowlBuster.Landings;
using BowlBuster.Platforms;
using BowlBuster.Recordings;

namespace BowlBuster.Tests.Landings;

public class ModelNamersTests
{
    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;
    private static readonly ModelPoolProfile Pools = Platform.Pools;
    private static readonly ModelPoolShape EightMatrices = new(0x4A, 8);
    private const uint Address = 0x700000;

    private static RegionName? Name(uint caller, uint size, uint offset)
    {
        PlacedBlock block = new(0, 0, Address - 0xC, Address, size, new AllocRequest(size, 0x10, Address, caller));
        return new RegionNamer(Platform, null).Name(new LandingRegion(RegionKind.Block, block, offset), null, []);
    }

    private static RegionName? InPool(uint offset) => Name(Platform.Sites.ModelPool, Pools.BlockSize(EightMatrices), offset);

    private static RegionName? Standalone(uint matrices, uint offset) => Name(Platform.Sites.ModelInstance, (matrices * 0x40) + 0xA0, offset);

    [Fact]
    public void Name_InAPoolsMatrices_NamesTheInstanceAndMatrix() =>
        Assert.Equal(new ModelMatrixName(EightMatrices, 2, 3, 0x10), InPool((2 * 8 * 0x40) + (3 * 0x40) + 0x10));

    [Fact]
    public void Name_InAPoolsHeader_NamesTheField() =>
        Assert.Equal(new ModelPoolHeaderName(EightMatrices, 4, Pools.HeaderFields.FieldAt(4)), InPool(Pools.MatrixBytes(EightMatrices) + 4));

    [Fact]
    public void Name_InAPoolInstance_NamesTheInstanceAndField()
    {
        var name = Assert.IsType<ModelInstanceName>(InPool(Pools.MatrixBytes(EightMatrices) + 0xC + 0xA0 + 0x4C));

        Assert.Equal((EightMatrices, 1, 0x4Cu, "flags"), (name.Pool, name.Instance, name.OffsetInInstance, name.Field?.Name));
    }

    [Fact]
    public void Name_PoolOfNoShapesSize_IsUnknown() =>
        Assert.Equal(new UnknownRegionName(Platform.Sites.ModelPool), Name(Platform.Sites.ModelPool, 0x1000, 0));

    [Fact]
    public void Name_InAStandaloneInstancesMatrices_NamesTheMatrix() =>
        Assert.Equal(new ModelMatrixName(null, 0, 1, 0x8), Standalone(2, 0x48));

    [Fact]
    public void Name_InAStandaloneInstance_NamesTheField()
    {
        var name = Assert.IsType<ModelInstanceName>(Standalone(2, 0x80 + 0x54));

        Assert.Equal((null, 0x54u, "mat"), (name.Pool, name.OffsetInInstance, name.Field?.Name));
    }

    [Fact]
    public void Name_InstanceBytesNoFieldCovers_ReachTheElement() =>
        Assert.Equal(NamingDepth.Element, Standalone(0, 0x44)!.Depth);

    [Theory]
    [InlineData(0x9Cu)]
    [InlineData(0xA0u + 0x20)]
    public void Name_StandaloneBlockThatIsntMatricesAndAnInstance_IsUnknown(uint size) =>
        Assert.Equal(new UnknownRegionName(Platform.Sites.ModelInstance), Name(Platform.Sites.ModelInstance, size, 0));

    [Fact]
    public void FieldLists_OfThePools_AreInOrderInsideTheirRecordAndDontOverlap()
    {
        foreach ((IReadOnlyList<LiveField> fields, uint size) in new[] { (Pools.HeaderFields, Pools.HeaderSize), (Pools.InstanceFields, Pools.InstanceSize) })
        {
            Assert.All(fields, field => Assert.True(field.End <= size, field.Name));
            Assert.All(fields.Zip(fields.Skip(1)), pair => Assert.True(pair.First.End <= pair.Second.Offset, pair.Second.Name));
        }
    }
}
