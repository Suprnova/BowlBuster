using BowlBuster.Platforms;
using BowlBuster.Recordings;
using System.Buffers.Binary;

namespace BowlBuster.Landings;

/// <summary>
/// Names a live object array down to the object and its field.
/// </summary>
/// <remarks>
/// The array's type is the site's own when it has one, else the type byte of the array's first object in the load's
/// capture. Every object of an array holds the array's type byte, so an object that doesn't, or a block whose size isn't
/// a whole number of objects, has no name. An object's asset is looked up by its ID in the load's archives, then in the
/// archives the game loaded at boot.
/// </remarks>
/// <param name="layouts">The live layouts.</param>
/// <param name="site">The array's site.</param>
internal sealed class LiveObjectNamer(LiveLayouts layouts, LiveArraySite site) : IBlockNamer
{
    private const uint IdOffset = 0x4;
    private const uint TypeOffset = 0x8;

    public RegionName? Name(PlacedBlock block, uint offset, NamingContext context)
    {
        if (TypeOf(block, context.Load?.Capture) is not { } type || block.Size % type.Size is not 0) return null;

        uint element = offset / type.Size;
        uint recorded = block.Request.Address + (element * type.Size);
        uint? id = null;

        if (context.Load?.Capture is { } capture)
        {
            if (site.Type is null && ByteAt(capture, recorded + TypeOffset) != type.Id) return null;
            id = WordAt(capture, recorded + IdOffset) is { } word and not 0 ? word : null;
        }

        AssetRef? asset = id is { } known && context.Layers is { } disc
            ? disc.FindAsset(context.Load!.Archives, known) ?? disc.FindAsset(layouts.BootArchives, known)
            : null;
        uint inObject = offset - (element * type.Size);
        return new LiveObjectName(type, (int)element, id, asset, inObject, type.FieldAt(inObject));
    }

    private LiveType? TypeOf(PlacedBlock block, ILoadCapture? capture) =>
        site.Type is { } fixedType ? layouts.Find(fixedType)
        : capture is not null && ByteAt(capture, block.Request.Address + TypeOffset) is { } read ? layouts.Find(read)
        : null;

    private static byte? ByteAt(ILoadCapture capture, uint address)
    {
        Span<byte> value = stackalloc byte[1];
        return capture.TryRead(address, value) ? value[0] : null;
    }

    private static uint? WordAt(ILoadCapture capture, uint address)
    {
        Span<byte> value = stackalloc byte[sizeof(uint)];
        return capture.TryRead(address, value) ? BinaryPrimitives.ReadUInt32LittleEndian(value) : null;
    }
}
