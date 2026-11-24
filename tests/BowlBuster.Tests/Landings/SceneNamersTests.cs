using BowlBuster.Landings;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Tests.Recordings;

namespace BowlBuster.Tests.Landings;

public class SceneNamersTests
{
    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;
    private static readonly SceneStructures Scene = Platform.Scene;
    private const uint Address = 0x700000;
    private const uint ArraySite = 0x68F3B;
    private const byte GroupType = 0x11;
    private const uint GroupSize = 0x24;

    private static PlacedBlock Block(uint address, uint size, uint caller) =>
        new(0, 0, address - 0xC, address, size, new AllocRequest(size, 0x10, address, caller));

    private static RegionName? Name(PlacedBlock block, uint offset, ILoadCapture? capture = null, IReadOnlyList<PlacedBlock>? live = null) =>
        new RegionNamer(Platform, null).Name(new LandingRegion(RegionKind.Block, block, offset), new LoadContext(capture, []), live ?? [block]);

    [Fact]
    public void Name_InTheScene_NamesTheField() =>
        Assert.Equal(new SceneName(0x72, Scene.Scene.FieldAt(0x70)), Name(Block(Address, 0x4F0, Scene.SceneSite), 0x72));

    [Fact]
    public void Name_SceneBytesNoFieldCovers_ReachTheKind() =>
        Assert.Equal(NamingDepth.Kind, Name(Block(Address, 0x4F0, Scene.SceneSite), 0x4)!.Depth);

    [Fact]
    public void Name_SceneOfAnotherSize_IsUnknown() =>
        Assert.Equal(new UnknownRegionName(Scene.SceneSite), Name(Block(Address, 0x400, Scene.SceneSite), 0x4));

    [Fact]
    public void Name_InTheEnv_IsTheEnv() =>
        Assert.Equal(new EnvName(0x10), Name(Block(Address, 0x40, Scene.EnvSite), 0x10));

    [Theory]
    [InlineData("dyns", 0x18BE47u)]
    [InlineData("act_ents", 0x18BE94u)]
    public void Name_InAScenePointerArray_NamesTheArrayAndEntry(string array, uint caller) =>
        Assert.Equal(new PointerEntryName(array, 2, null), Name(Block(Address, 0x10, caller), 0x9));

    [Theory]
    [InlineData(0x0u, 0, 0, "prev")]
    [InlineData(0x6Cu, 0, 3, null)]
    [InlineData(0x84u, 0, null, null)]
    [InlineData(0x98u + 0x24, 1, 1, "object")]
    public void Name_InTheWalkRecords_NamesTheCategoryRecordAndField(uint offset, int category, int? record, string? field)
    {
        var name = Assert.IsType<WalkRecordName>(Name(Block(Address, 0x8A0, Scene.WalkRecordsSite), offset));

        Assert.Equal((category, record, field), (name.Category, name.Record, name.Field?.Name));
    }

    [Fact]
    public void Name_PastTheLastWalkCategory_IsUnknown() =>
        Assert.Equal(new UnknownRegionName(Scene.WalkRecordsSite), Name(Block(Address, 0x900, Scene.WalkRecordsSite), 0x8A0));

    [Fact]
    public void Name_InAGroupsItems_NamesTheGroupThatHoldsThemAndTheItem()
    {
        const uint items = Address + 0x1000;
        PlacedBlock groups = Block(Address, 2 * GroupSize, ArraySite);
        PlacedBlock array = Block(items, 8, Scene.GroupItemsSite);
        ByteCapture capture = new ByteCapture(Address, 0x1010)
            .Byte(Address + 8, GroupType).Word(Address + 4, 0x100)
            .Byte(Address + GroupSize + 8, GroupType).Word(Address + GroupSize + 4, 0x200).Word(Address + GroupSize + 0x18, items)
            .Word(items + 4, Address);

        var name = Assert.IsType<PointerEntryName>(Name(array, 4, capture, [groups, array]));

        LiveObjectName owner = Assert.IsType<LiveObjectName>(name.Owner);
        Assert.Equal(("items", 1), (name.Array, name.Entry));
        Assert.Equal((1, 0x200u, "items"), (owner.Element, owner.Id, owner.Field?.Name));
        Assert.Equal(0x100u, Assert.IsType<LiveObjectName>(name.Target).Id);
    }

    [Fact]
    public void Name_InTheParticlePool_NamesTheChunk() =>
        Assert.Equal(new ParticlePoolName(3, 0x10), Name(Block(Address, 0x28000, Scene.ParticlePoolSite), (3 * 0x1400) + 0x10));

    [Fact]
    public void Name_ParticlePoolThatIsntWholeChunks_IsUnknown() =>
        Assert.Equal(new UnknownRegionName(Scene.ParticlePoolSite), Name(Block(Address, 0x1000, Scene.ParticlePoolSite), 0));

    [Fact]
    public void Name_InTheParticleRecords_NamesTheRecordAndField() =>
        Assert.Equal(new RecordArrayName("particles", 2, 0x1C, Scene.RecordArrays[0].Record.FieldAt(0x1C)), Name(Block(Address, 0xC000, 0x73E61), (2 * 0x30) + 0x1C));

    [Fact]
    public void Name_InTheStaticSimpleManagers_NamesTheRecordAndField() =>
        Assert.Equal(("smgrs", 1, "ent"), Assert.IsType<RecordArrayName>(Name(Block(Address, 0x80, 0x99997), 0x40 + 0x38)) is var name ? (name.Array, name.Record, name.Field?.Name) : default);

    [Fact]
    public void Name_InAPointerList_NamesTheEntry() =>
        Assert.Equal(new PointerEntryName("pointer list", 1, null), Name(Block(Address, 8, 0x184B90), 4));

    [Fact]
    public void Name_RecordArrayThatIsntWholeRecords_IsUnknown() =>
        Assert.Equal(new UnknownRegionName(0x73E61), Name(Block(Address, 0x40, 0x73E61), 0));

    [Fact]
    public void Name_PlayerEntity_IsAPlayerObjectOfItsOwnSize()
    {
        var name = Assert.IsType<LiveObjectName>(Name(Block(Address, 0x2B8, Platform.Sites.PlayerEntity), 0x2B4));

        Assert.Equal((0x03, 0, 0x2B4u, (LiveField?)null), (name.Type.Id, name.Element, name.OffsetInObject, name.Field));
    }
}
