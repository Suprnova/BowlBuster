namespace BowlBuster.Platforms;

/// <summary>
/// A site that allocates an array of pointers.
/// </summary>
/// <param name="Caller">The allocation's return address.</param>
/// <param name="Name">The array's name, as the field that holds it is named, or what the array is for a site that serves many owners.</param>
public sealed record PointerArraySite(uint Caller, string Name);

/// <summary>
/// A site that allocates an array of fixed-size records.
/// </summary>
/// <param name="Caller">The allocation's return address.</param>
/// <param name="Name">The array's name.</param>
/// <param name="Record">A record's layout.</param>
public sealed record RecordArraySite(uint Caller, string Name, RecordLayout Record);

/// <summary>
/// The scene's own structures in heap 0, beyond its live objects (2.4).
/// </summary>
/// <param name="SceneSite">The site of the <c>zScene</c> record.</param>
/// <param name="Scene">The <c>zScene</c> record's layout.</param>
/// <param name="EnvSite">The site of the scene's <c>xEnv</c>, whose layout isn't known.</param>
/// <param name="PointerArrays">The arrays of pointers: the base array, the scene's entity arrays, and the game's growable pointer lists.</param>
/// <param name="GroupItemsSite">The site of a group's item array: pointers to its items' live bases.</param>
/// <param name="GroupType">The live type byte of a group.</param>
/// <param name="GroupItemsOffset">The offset of the live group's pointer to its item array.</param>
/// <param name="WalkRecordsSite">The site of the walk records.</param>
/// <param name="WalkCategories">The number of records in each walk category, in block order. Each category's records are followed by a list of its count plus 2 words.</param>
/// <param name="WalkRecord">A walk record's layout.</param>
/// <param name="ParticlePoolSite">The site of the particle pool: one buffer of equal chunks that the particle clients store their elements in.</param>
/// <param name="ParticleChunkSize">The size of one of the particle pool's chunks.</param>
/// <param name="RecordArrays">The arrays of fixed-size records.</param>
public sealed record SceneStructures(
    uint SceneSite,
    RecordLayout Scene,
    uint EnvSite,
    IReadOnlyList<PointerArraySite> PointerArrays,
    uint GroupItemsSite,
    byte GroupType,
    uint GroupItemsOffset,
    uint WalkRecordsSite,
    IReadOnlyList<int> WalkCategories,
    RecordLayout WalkRecord,
    uint ParticlePoolSite,
    uint ParticleChunkSize,
    IReadOnlyList<RecordArraySite> RecordArrays)
{
    /// <summary>
    /// The Xbox structures.
    /// </summary>
    public static SceneStructures Xbox { get; } = new(
        0x73A99,
        new RecordLayout(0x4F0,
        [
            new("sceneId", 0x0, 4),
            new("num_act_ents", 0x1C, 2),
            new("num_trigs_allocd", 0x1E, 2),
            new("num_stats_allocd", 0x20, 2),
            new("num_dyns_allocd", 0x22, 2),
            new("num_npcs_allocd", 0x24, 2),
            new("trigs", 0x28, 4),
            new("stats", 0x2C, 4),
            new("dyns", 0x30, 4),
            new("npcs", 0x34, 4),
            new("act_ents", 0x38, 4),
            new("env", 0x3C, 4),
            new("pendingPortal", 0x68, 4),
            new("baseCount", 0x6C, 4),
            new("bases", 0x70, 4),
            new("allocatedBaseCount", 0x118, 4),
            new("typeArrays", 0x2B0, 31 * 4),
            new("allocatedBases", 0x34C, 4),
        ]),
        0x73AC9,
        [
            new(0x74014, "bases"),
            new(0x18BE0A, "trigs"),
            new(0x18BE28, "stats"),
            new(0x18BE47, "dyns"),
            new(0x18BE66, "npcs"),
            new(0x18BE94, "act_ents"),
            new(0x184B90, "pointer list"),
        ],
        0x176466,
        0x11,
        0x18,
        0x188FC8,
        [4, 8, 12, 16, 12, 8],
        new RecordLayout(0x20, [new("prev", 0x0, 4), new("object", 0x4, 4), new("flags", 0x8, 4)]),
        0x191B52,
        0x1400,
        [
            new(0x73E61, "particles", new RecordLayout(0x30, [new("position", 0x0, 0xC), new("velocity", 0x10, 0xC), new("lifetime", 0x1C, 4)])),
            new(0x170D44, "queue pool", new RecordLayout(0x2C, [])),
            new(0x99997, "smgrs", new RecordLayout(0x40,
            [
                new("worldBound.center", 0x0, 0xC),
                new("worldBound.r", 0xC, 4),
                new("noRenderDist", 0x10, 4),
                new("lodDist0", 0x14, 4),
                new("fadeDist", 0x18, 4),
                new("flags", 0x1C, 4),
                new("lodBucket", 0x20, 8),
                new("lodAtomic", 0x28, 8),
                new("mat", 0x30, 4),
                new("model", 0x34, 4),
                new("ent", 0x38, 4),
                new("lkit", 0x3C, 4),
            ])),
        ]);
}
