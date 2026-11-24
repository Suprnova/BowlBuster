using BowlBuster.Platforms;
using BowlBuster.Recordings;

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
        if (TypeOf(block, context.Load?.Capture) is not { } type) return null;

        uint size = site.ObjectSize ?? type.Size;
        if (block.Size % size is not 0) return null;

        uint element = offset / size;
        uint recorded = block.Request.Address + (element * size);
        uint? id = null;

        if (context.Load?.Capture is { } capture)
        {
            if (site.Type is null && capture.ByteAt(recorded + TypeOffset) != type.Id) return null;
            id = capture.WordAt(recorded + IdOffset) is { } word and not 0 ? word : null;
        }

        AssetRef? asset = id is { } known ? context.FindAsset(known) : null;
        uint inObject = offset - (element * size);
        return new LiveObjectName(type, (int)element, id, asset, inObject, type.FieldAt(inObject));
    }

    private LiveType? TypeOf(PlacedBlock block, ILoadCapture? capture) =>
        site.Type is { } fixedType ? layouts.Find(fixedType)
        : capture is not null && capture.ByteAt(block.Request.Address + TypeOffset) is { } read ? layouts.Find(read)
        : null;
}
