using BowlBuster.Platforms;
using BowlBuster.Recordings;

namespace BowlBuster.Landings;

/// <summary>
/// An asset of an archive layer, as a name points at it.
/// </summary>
/// <param name="Id">The asset's ID.</param>
/// <param name="Name">The asset's name as the archive stores it.</param>
/// <param name="Type">The asset's type.</param>
public readonly record struct AssetRef(uint Id, string Name, string Type);

/// <summary>
/// What a live block holds at an offset, as far as the block's kind can say.
/// </summary>
public abstract record RegionName
{
    /// <summary>How far the name reaches.</summary>
    public abstract NamingDepth Depth { get; }
}

/// <summary>
/// How far a <see cref="RegionName"/> reaches into its block, from the allocation's caller alone to the field.
/// </summary>
public enum NamingDepth
{
    /// <summary>Only the allocation's caller: an unknown region.</summary>
    Caller,

    /// <summary>What kind of block it is.</summary>
    Kind,

    /// <summary>Which element of the block, by index.</summary>
    Element,

    /// <summary>Which object or asset the element is.</summary>
    Identity,

    /// <summary>Which field of the object, or bytes that have no fields, such as the padding between two assets.</summary>
    Field,
}

/// <summary>
/// Inside an asset of a class-1 archive layer.
/// </summary>
/// <param name="Layer">The archive and layer.</param>
/// <param name="Asset">The asset.</param>
/// <param name="OffsetInAsset">The offset from the asset's first byte.</param>
public sealed record LayerAssetName(LayerId Layer, AssetRef Asset, uint OffsetInAsset) : RegionName
{
    /// <inheritdoc/>
    public override NamingDepth Depth => NamingDepth.Identity;

    /// <summary>Whether the offset is in the asset's first word, which holds a base asset's own ID.</summary>
    public bool IsFirstWord => OffsetInAsset < sizeof(uint);
}

/// <summary>
/// In the padding between two assets of a class-1 archive layer.
/// </summary>
/// <param name="Layer">The archive and layer.</param>
/// <param name="Before">The asset that ends where the padding starts.</param>
/// <param name="After">The asset that starts where the padding ends.</param>
/// <param name="OffsetInPadding">The offset from the padding's first byte.</param>
public sealed record LayerPaddingName(LayerId Layer, AssetRef Before, AssetRef After, uint OffsetInPadding) : RegionName
{
    /// <inheritdoc/>
    public override NamingDepth Depth => NamingDepth.Field;
}

/// <summary>
/// In a class-1 layer's block past its last asset, where the block's size is rounded up from the layer's image.
/// </summary>
/// <param name="Layer">The archive and layer.</param>
/// <param name="Last">The layer's last asset.</param>
/// <param name="OffsetPastEnd">The offset from the image's end.</param>
public sealed record LayerSlackName(LayerId Layer, AssetRef Last, uint OffsetPastEnd) : RegionName
{
    /// <inheritdoc/>
    public override NamingDepth Depth => NamingDepth.Field;
}

/// <summary>
/// Inside an object of a live object array.
/// </summary>
/// <param name="Type">The array's type.</param>
/// <param name="Element">The object's index in the array.</param>
/// <param name="Id">The object's ID from the load's capture, or <see langword="null"/> when there's no capture or it holds 0.</param>
/// <param name="Asset">The asset of that ID in the load's archives, or <see langword="null"/> when the disc doesn't name it.</param>
/// <param name="OffsetInObject">The offset from the object's first byte.</param>
/// <param name="Field">The field that covers the offset, or <see langword="null"/> when the layout names none there.</param>
public sealed record LiveObjectName(LiveType Type, int Element, uint? Id, AssetRef? Asset, uint OffsetInObject, LiveField? Field) : RegionName
{
    /// <inheritdoc/>
    public override NamingDepth Depth => Field is not null ? NamingDepth.Field
        : Id is not null ? NamingDepth.Identity
        : NamingDepth.Element;
}

/// <summary>
/// In a record of an archive's asset directory.
/// </summary>
/// <param name="Archive">The archive, named as a recording names it.</param>
/// <param name="Record">The record's index.</param>
/// <param name="Asset">The record's asset.</param>
/// <param name="OffsetInRecord">The offset from the record's first byte.</param>
/// <param name="Field">The field that covers the offset, or <see langword="null"/> when the layout names none there.</param>
public sealed record AssetDirectoryName(string Archive, int Record, AssetRef Asset, uint OffsetInRecord, LiveField? Field) : RegionName
{
    /// <inheritdoc/>
    public override NamingDepth Depth => Field is not null ? NamingDepth.Field : NamingDepth.Identity;
}

/// <summary>
/// In a slot of the object lookup table, which holds an ID and a pointer to its live base.
/// </summary>
/// <param name="Slot">The slot's index.</param>
/// <param name="IsPointer">Whether the offset is in the slot's pointer rather than its ID.</param>
/// <param name="Id">The slot's ID from the load's capture, or <see langword="null"/> when there's no capture or the slot is empty.</param>
/// <param name="Asset">The asset of that ID in the load's archives, or <see langword="null"/> when the disc doesn't name it.</param>
public sealed record LookupEntryName(int Slot, bool IsPointer, uint? Id, AssetRef? Asset) : RegionName
{
    /// <inheritdoc/>
    public override NamingDepth Depth => NamingDepth.Field;
}

/// <summary>
/// In an entry of the base array, which points at a live base.
/// </summary>
/// <param name="Entry">The entry's index.</param>
/// <param name="Target">What the entry points at in the load's capture, or <see langword="null"/> when there's no capture or it points at no live block.</param>
public sealed record BaseEntryName(int Entry, RegionName? Target) : RegionName
{
    /// <inheritdoc/>
    public override NamingDepth Depth => NamingDepth.Field;
}

/// <summary>
/// In a block no layout names yet, known only by the return address of its allocation (4.3): an unknown region (5.6).
/// </summary>
/// <param name="Caller">The allocation's caller.</param>
public sealed record UnknownRegionName(uint Caller) : RegionName
{
    /// <inheritdoc/>
    public override NamingDepth Depth => NamingDepth.Caller;
}
