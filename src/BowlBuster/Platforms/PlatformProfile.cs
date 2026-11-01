namespace BowlBuster.Platforms;

/// <summary>
/// The addresses and constants of one platform's build of the game.
/// </summary>
/// <param name="Heap0">The heap that holds everything a landing can reach.</param>
/// <param name="PlayerEntitySize">The size in bytes of the player entity that every scene load allocates and never frees.</param>
/// <param name="Pools">The constants of the model pools.</param>
/// <param name="Sites">The allocation sites the simulator tells apart.</param>
/// <param name="Platform">The platform's name in a recording. A recording made on another platform can't be replayed on this profile.</param>
/// <param name="Footprint">What the stale write touches.</param>
public sealed record PlatformProfile(
    HeapProfile Heap0,
    uint PlayerEntitySize,
    ModelPoolProfile Pools,
    AllocationSites Sites,
    string Platform,
    FootprintProfile Footprint)
{
    private const uint ScaleWord = 0x40833333;

    /// <summary>
    /// The Xbox NTSC-U retail build, which the Xbox UK build shares.
    /// </summary>
    public static PlatformProfile XboxNtscU { get; } = new(
        new HeapProfile(0xE00000, 12, 16, 12),
        0x2B8,
        new ModelPoolProfile([new(0x31, 0x40), new(0x4A, 8), new(0x144, 1)], 0xC, 0xA0, 0x40, 0x40),
        new AllocationSites(0x72670, 0x182B2A, 0xAF43D, 0x192860, 0x186603),
        "xbox",
        new FootprintProfile(
        [
            new(0x38, 4, 0),
            new(0x58, 4, ScaleWord),
            new(0x5C, 4, ScaleWord),
            new(0x60, 4, ScaleWord),
            new(0x10, 4, null),
            new(0x14, 4, null),
            new(0x2C, 4, null),
            new(0x30, 4, null),
            new(0x34, 4, null),
            new(0x3C, 4, null),
            new(0x4C, 2, null),
            new(0x4E, 1, null),
            new(0x54, 4, null),
            new(0x64, 4, null),
            new(0x68, 4, null),
            new(0x6C, 4, null),
            new(0x70, 4, null),
            new(0x74, 4, null),
            new(0x78, 4, null),
        ]));
}
