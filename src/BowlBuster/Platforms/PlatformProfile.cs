namespace BowlBuster.Platforms;

/// <summary>
/// The addresses and constants of one platform's build of the game.
/// </summary>
/// <param name="Heap0">The heap that holds everything a landing can reach.</param>
/// <param name="PlayerEntitySize">The size in bytes of the player entity that every scene load allocates and never frees.</param>
public sealed record PlatformProfile(HeapProfile Heap0, uint PlayerEntitySize)
{
    /// <summary>
    /// The Xbox NTSC-U retail build, which the Xbox UK build shares.
    /// </summary>
    public static PlatformProfile XboxNtscU { get; } = new(new HeapProfile(0xE00000, 12, 16, 12), 0x2B8);
}
