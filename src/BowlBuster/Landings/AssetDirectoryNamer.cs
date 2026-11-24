using BowlBuster.Platforms;
using BowlBuster.Recordings;

namespace BowlBuster.Landings;

/// <summary>
/// Names an archive's asset directory down to the record's asset and field.
/// </summary>
/// <remarks>
/// A recording doesn't say which archive a directory is for, so the directory is the one archive of the load whose
/// asset count fills the block, a record per asset. When two have that count, the capture's first record ID tells them
/// apart; without a capture, or when it doesn't, the block has no name.
/// </remarks>
/// <param name="record">The layout of a directory record.</param>
internal sealed class AssetDirectoryNamer(RecordLayout record) : IBlockNamer
{
    public RegionName? Name(PlacedBlock block, uint offset, NamingContext context)
    {
        if (context is not { Layers: { } disc, Load: { } load } || block.Size % record.Size is not 0) return null;

        uint count = block.Size / record.Size;
        (string Archive, IReadOnlyList<AssetRef> Assets)[] candidates =
        [
            .. load.Archives
                .Select(archive => (Archive: archive, Assets: disc.DirectoryOf(archive)))
                .Where(candidate => candidate.Assets?.Count == count)
                .Select(static candidate => (candidate.Archive, candidate.Assets!)),
        ];
        if (candidates.Length > 1 && load.Capture?.WordAt(block.Request.Address) is { } firstId)
            candidates = [.. candidates.Where(candidate => candidate.Assets[0].Id == firstId)];
        if (candidates is not [var (archive, assets)]) return null;

        uint index = offset / record.Size;
        uint inRecord = offset % record.Size;
        return new AssetDirectoryName(archive, (int)index, assets[(int)index], inRecord, record.FieldAt(inRecord));
    }
}
