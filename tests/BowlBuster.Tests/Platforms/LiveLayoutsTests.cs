using BowlBuster.Platforms;

namespace BowlBuster.Tests.Platforms;

public class LiveLayoutsTests
{
    private static readonly LiveLayouts Layouts = LiveLayouts.Xbox;

    public static TheoryData<byte> TypeIds => [.. Layouts.Types.Select(static type => type.Id)];

    [Theory]
    [MemberData(nameof(TypeIds))]
    public void Fields_OfEveryType_AreInOrderInsideTheObjectAndDontOverlap(byte id)
    {
        LiveType type = Layouts.Find(id)!;

        Assert.All(type.Fields, field => Assert.True(field.Size > 0 && field.End <= type.Size, $"{type.Name}.{field.Name}"));
        Assert.All(type.Fields.Zip(type.Fields.Skip(1)), pair => Assert.True(pair.First.End <= pair.Second.Offset, $"{type.Name}: {pair.First.Name}, {pair.Second.Name}"));
    }

    [Fact]
    public void Sites_TypesTheyFix_AreInTheTables() =>
        Assert.All(Layouts.Sites.Where(static site => site.Type is not null), site => Assert.NotNull(Layouts.Find(site.Type!.Value)));

    [Fact]
    public void Find_TypeNoTableHas_IsNull() =>
        Assert.Null(Layouts.Find(0xFF));

    [Theory]
    [InlineData(0x18u, "count")]
    [InlineData(0x19u, "count")]
    [InlineData(0x1Bu, null)]
    public void FieldAt_AnOffset_IsTheFieldThatCoversIt(uint offset, string? field) =>
        Assert.Equal(field, Layouts.Find(0x16)!.FieldAt(offset)?.Name);
}
