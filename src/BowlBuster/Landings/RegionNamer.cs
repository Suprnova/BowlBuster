using BowlBuster.Platforms;

namespace BowlBuster.Landings;

/// <summary>
/// Names what a landing word lies in, with a namer per block kind chosen by the block's allocation site.
/// </summary>
/// <remarks>
/// A class-1 archive layer is named down to its asset, padding or slack from the disc, and an asset directory down to
/// the record's asset and field; a live object array down to the object, its asset and its field from the load's
/// capture; the lookup table down to the slot and its entry's asset; an array of pointers to live bases (the base array,
/// the scene's entity arrays, a group's items) down to the entry and what it points at; a model pool or standalone
/// instance down to the matrix, the header or the instance's field; the scene's record, its <c>xEnv</c> and the walk
/// records down to their fields; and the particle pool down to the chunk. Any other block, or a block its namer can't tell, is an unknown region named by its
/// caller: a wrong guess is worse than an unknown.
/// </remarks>
public sealed class RegionNamer
{
    private readonly ILayerSource? layers;
    private readonly IReadOnlyList<string> bootArchives;
    private readonly Dictionary<uint, IBlockNamer> namers;

    /// <summary>
    /// Creates a namer.
    /// </summary>
    /// <param name="profile">The platform's constants.</param>
    /// <param name="layers">The archive layers on disc, or <see langword="null"/> when there are none to read.</param>
    public RegionNamer(PlatformProfile profile, ILayerSource? layers)
    {
        ArgumentNullException.ThrowIfNull(profile);

        this.layers = layers;
        bootArchives = profile.Live.BootArchives;
        namers = profile.Live.Sites.ToDictionary(static site => site.Caller, IBlockNamer (site) => new LiveObjectNamer(profile.Live, site));
        namers[profile.Sites.ArchiveLayer] = new FirstNamer(new LayerNamer(), new AssetDirectoryNamer(profile.Live.DirectoryRecord));
        namers[profile.Sites.LookupTable] = new LookupTableNamer();
        foreach (PointerArraySite array in profile.Scene.PointerArrays) namers[array.Caller] = new PointerArrayNamer(this, array.Name);
        namers[profile.Scene.GroupItemsSite] = new GroupItemsNamer(this, profile.Live, profile.Scene);
        namers[profile.Scene.SceneSite] = new SceneNamer(profile.Scene.Scene);
        namers[profile.Scene.EnvSite] = new EnvNamer();
        namers[profile.Scene.WalkRecordsSite] = new WalkRecordsNamer(profile.Scene);
        namers[profile.Scene.ParticlePoolSite] = new ParticlePoolNamer(profile.Scene.ParticleChunkSize);
        namers[profile.Sites.ModelPool] = new ModelPoolNamer(profile.Pools);
        namers[profile.Sites.ModelInstance] = new ModelInstanceNamer(profile.Pools);
    }

    /// <summary>
    /// Names the block a word's first byte lies in.
    /// </summary>
    /// <param name="region">What the word's first byte lies in.</param>
    /// <param name="load">The load that allocated the block, or <see langword="null"/> when nothing is known of it.</param>
    /// <param name="live">The live blocks in address order, as <see cref="BlockTracker.Live"/> holds them, which pointers in the block resolve against.</param>
    /// <returns>The name, or <see langword="null"/> outside a live block.</returns>
    public RegionName? Name(LandingRegion region, LoadContext? load, IReadOnlyList<PlacedBlock> live) =>
        region is { Kind: RegionKind.Block, Block: { } block } ? Name(block, region.Offset, new NamingContext(layers, load, live, bootArchives)) : null;

    internal RegionName Name(PlacedBlock block, uint offset, NamingContext context) =>
        namers.TryGetValue(block.Request.Caller, out IBlockNamer? namer) && namer.Name(block, offset, context) is { } name
            ? name
            : new UnknownRegionName(block.Request.Caller);
}
