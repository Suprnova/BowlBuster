using BowlBuster.Platforms;

namespace BowlBuster.Landings;

/// <summary>
/// Names an array of pointers to live bases, each entry by what it points at.
/// </summary>
/// <param name="namer">Names what an entry points at.</param>
/// <param name="array">The array's name.</param>
internal sealed class PointerArrayNamer(RegionNamer namer, string array) : IBlockNamer
{
    public RegionName? Name(PlacedBlock block, uint offset, NamingContext context) =>
        block.Size % sizeof(uint) is 0 ? new PointerEntryName(array, (int)(offset / sizeof(uint)), Target(namer, block, offset, context)) : null;

    /// <summary>
    /// Names what the pointer at an offset of a block points at, in the same load.
    /// </summary>
    /// <returns>The name, or <see langword="null"/> when there's no capture, the pointer is null, or it points at no other live block.</returns>
    internal static RegionName? Target(RegionNamer namer, PlacedBlock block, uint offset, NamingContext context) =>
        context.Load?.Capture?.WordAt(block.Request.Address + (offset & ~3u)) is { } pointer and not 0
        && context.BlockAt(block.Position, pointer) is { } held && held != block
            ? namer.Name(held, pointer - held.Request.Address, context)
            : null;
}

/// <summary>
/// Names a group's item array: pointers to its items' live bases, owned by the group whose live item pointer holds it.
/// </summary>
/// <param name="namer">Names the items and the group.</param>
/// <param name="live">The live layouts, which give the arrays' sites.</param>
/// <param name="scene">The scene's structures, which give the group's type and its item pointer's offset.</param>
internal sealed class GroupItemsNamer(RegionNamer namer, LiveLayouts live, SceneStructures scene) : IBlockNamer
{
    private const uint TypeOffset = 0x8;

    public RegionName? Name(PlacedBlock block, uint offset, NamingContext context) =>
        block.Size % sizeof(uint) is 0
            ? new PointerEntryName("items", (int)(offset / sizeof(uint)), PointerArrayNamer.Target(namer, block, offset, context), Owner(block, context))
            : null;

    private RegionName? Owner(PlacedBlock items, NamingContext context)
    {
        if (context.Load?.Capture is not { } capture) return null;

        LiveType group = live.Find(scene.GroupType)!;
        return context.Live
            .Where(block => block.Position == items.Position
                && live.Sites.Any(site => site.Caller == block.Request.Caller)
                && capture.ByteAt(block.Request.Address + TypeOffset) == scene.GroupType)
            .SelectMany(block => Enumerable
                .Range(0, (int)(block.Size / group.Size))
                .Select(element => (Block: block, Offset: ((uint)element * group.Size) + scene.GroupItemsOffset)))
            .Where(field => capture.WordAt(field.Block.Request.Address + field.Offset) == items.Request.Address)
            .Select(field => namer.Name(field.Block, field.Offset, context))
            .FirstOrDefault();
    }
}

/// <summary>
/// Names the scene's <c>zScene</c> record.
/// </summary>
/// <param name="layout">The record's layout.</param>
internal sealed class SceneNamer(RecordLayout layout) : IBlockNamer
{
    public RegionName? Name(PlacedBlock block, uint offset, NamingContext context) =>
        block.Size == layout.Size ? new SceneName(offset, layout.FieldAt(offset)) : null;
}

/// <summary>
/// Names the scene's <c>xEnv</c>.
/// </summary>
internal sealed class EnvNamer : IBlockNamer
{
    public RegionName? Name(PlacedBlock block, uint offset, NamingContext context) => new EnvName(offset);
}

/// <summary>
/// Names the particle pool by chunk.
/// </summary>
/// <param name="chunkSize">The size of a chunk.</param>
internal sealed class ParticlePoolNamer(uint chunkSize) : IBlockNamer
{
    public RegionName? Name(PlacedBlock block, uint offset, NamingContext context) =>
        block.Size % chunkSize is 0 ? new ParticlePoolName((int)(offset / chunkSize), offset % chunkSize) : null;
}

/// <summary>
/// Names the walk records: each category's records, then its list of words.
/// </summary>
/// <param name="scene">The scene's structures, which give the categories and the record's layout.</param>
internal sealed class WalkRecordsNamer(SceneStructures scene) : IBlockNamer
{
    public RegionName? Name(PlacedBlock block, uint offset, NamingContext context)
    {
        RecordLayout record = scene.WalkRecord;
        uint start = 0;

        for (int category = 0; category < scene.WalkCategories.Count; category++)
        {
            uint count = (uint)scene.WalkCategories[category];
            uint records = count * record.Size;
            uint end = start + records + ((count + 2) * sizeof(uint));

            if (offset < end)
            {
                uint inCategory = offset - start;
                return inCategory < records
                    ? new WalkRecordName(category, (int)(inCategory / record.Size), inCategory % record.Size, record.FieldAt(inCategory % record.Size))
                    : new WalkRecordName(category, null, inCategory - records, null);
            }

            start = end;
        }

        return null;
    }
}
