namespace BowlBuster.Platforms;

/// <summary>
/// A site that allocates an array of pointers to live bases.
/// </summary>
/// <param name="Caller">The allocation's return address.</param>
/// <param name="Name">The array's name, as the field that holds it is named.</param>
public sealed record PointerArraySite(uint Caller, string Name);

/// <summary>
/// The scene's own structures in heap 0, beyond its live objects (2.4).
/// </summary>
/// <param name="SceneSite">The site of the <c>zScene</c> record.</param>
/// <param name="Scene">The <c>zScene</c> record's layout.</param>
/// <param name="EnvSite">The site of the scene's <c>xEnv</c>, whose layout isn't known.</param>
/// <param name="PointerArrays">The arrays of pointers to live bases, the base array among them.</param>
/// <param name="GroupItemsSite">The site of a group's item array: pointers to its items' live bases.</param>
/// <param name="GroupType">The live type byte of a group.</param>
/// <param name="GroupItemsOffset">The offset of the live group's pointer to its item array.</param>
/// <param name="WalkRecordsSite">The site of the walk records.</param>
/// <param name="WalkCategories">The number of records in each walk category, in block order. Each category's records are followed by a list of its count plus 2 words.</param>
/// <param name="WalkRecord">A walk record's layout.</param>
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
    RecordLayout WalkRecord)
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
        ],
        0x176466,
        0x11,
        0x18,
        0x188FC8,
        [4, 8, 12, 16, 12, 8],
        new RecordLayout(0x20, [new("prev", 0x0, 4), new("object", 0x4, 4), new("flags", 0x8, 4)]));
}
