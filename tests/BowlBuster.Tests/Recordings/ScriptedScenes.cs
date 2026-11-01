using BowlBuster.Memory;
using BowlBuster.Recordings;

namespace BowlBuster.Tests.Recordings;

/// <summary>
/// Invented scenes. They hold no game data: each is a list of requests shaped like a scene load.
/// </summary>
internal static class ScriptedScenes
{
    public const uint EntitySite = 0x72670;
    public const uint PoolSite = 0x182B2A;
    public const uint LayerSite = 0x192860;
    public const uint SphereSite = 0xAF43D;
    public const uint OtherModelSite = 0x23050;
    public const uint PlaySite = 0x590B0;
    public const uint LookupSite = 0x74031;

    public const uint EntitySize = 0x2B8;

    public static HeapSnapshot OriginStart { get; } =
        new([new HeapState(0x5C0030, 0, 0), new HeapState(0x6E6C48, 500, 0x126C18)], new HeapBlock(0x6E6990, EntitySize));

    public static HeapSnapshot TargetStart { get; } =
        new([new HeapState(0x5C0030, 0, 0), new HeapState(0x6E6F18, 501, 0x126EE8)], new HeapBlock(0x749D50, 0x20));

    /// <summary>
    /// The heap a load starts from after the given number of extra leaks past <see cref="OriginStart"/>.
    /// </summary>
    public static HeapSnapshot StartAfterLeaks(int leaks)
    {
        const uint leakCost = 720;
        uint added = (uint)leaks * leakCost;
        HeapState state = OriginStart.States[1];

        return OriginStart with { States = [OriginStart.States[0], new HeapState(state.Cursor + added, state.BlockCount + leaks, state.Used + added)] };
    }

    public static Scene Origin { get; } = new(
        "ORIG",
        [
            new Alloc(EntitySize, 0, EntitySite),
            new Push(),
            new Alloc(0x10000, 0x40, LayerSite, new LayerId("PLAY", 0)),
            new Push(),
            new Push(),
            new Alloc(208_556, 16, PoolSite),
            new Alloc(49_740, 16, PoolSite),
            new Alloc(72_588, 16, PoolSite),
            new Alloc(0x2000, 0x40, LayerSite, new LayerId("ORIG", 0)),
            new Grow(0x100),
            new Pool(0, 0, OtherModelSite),
            new Pool(0, 0, OtherModelSite),
            new FreePoolAlloc(0),
            new Pool(0, 0, SphereSite),
            new CutoffHere(),
            new Alloc(0x20, 0, PlaySite),
            new ExitScene(),
            new PopTo(1),
        ]);

    /// <summary>
    /// A small scene whose heap at the cutoff ends far below the origin's sphere, then reaches past it during play.
    /// </summary>
    public static Scene Filler { get; } = new(
        "FILL",
        [
            new Alloc(EntitySize, 0, EntitySite),
            new Push(),
            new Alloc(0x1000, 0x40, LayerSite, new LayerId("FILL", 0)),
            new CutoffHere(),
            new Alloc(0x80000, 0x40, PlaySite),
            new ExitScene(),
            new PopTo(1),
        ]);

    public static Scene Target { get; } = new(
        "TARG",
        [
            new Alloc(EntitySize, 0, EntitySite),
            new Push(),
            new Alloc(0x800, 0x40, LayerSite, new LayerId("PLAY", 1)),
            new Push(),
            new Push(),
            new Alloc(208_556, 16, PoolSite),
            new Alloc(49_740, 16, PoolSite),
            new Alloc(72_588, 16, PoolSite),
            new Alloc(0x60000, 0x40, LayerSite, new LayerId("TARG", 0)),
            new Grow(0x40),
            new Alloc(0x1C, 0, LookupSite),
            new CutoffHere(),
            new ExitScene(),
            new PopTo(1),
        ]);
}
