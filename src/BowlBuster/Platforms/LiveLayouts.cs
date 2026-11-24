namespace BowlBuster.Platforms;

/// <summary>
/// A named field of a live object.
/// </summary>
/// <param name="Name">The field's name, as rules claim it.</param>
/// <param name="Offset">The field's offset in the object.</param>
/// <param name="Size">The field's size in bytes.</param>
public sealed record LiveField(string Name, uint Offset, uint Size)
{
    /// <summary>The first offset past the field.</summary>
    public uint End => Offset + Size;
}

/// <summary>
/// A live object type: what the scene allocates one array of per type.
/// </summary>
/// <param name="Id">The type byte every object of the type holds at <c>+8</c>.</param>
/// <param name="Name">The type's name in the executable's type tables.</param>
/// <param name="Size">The size of one object.</param>
/// <param name="Fields">The fields the layout names, in offset order. Bytes no field covers are unnamed.</param>
public sealed record LiveType(byte Id, string Name, uint Size, IReadOnlyList<LiveField> Fields)
{
    /// <summary>
    /// Finds the field that covers an offset.
    /// </summary>
    /// <param name="offset">The offset in the object.</param>
    /// <returns>The field, or <see langword="null"/> when the layout names none there.</returns>
    public LiveField? FieldAt(uint offset) => Fields.FirstOrDefault(field => offset >= field.Offset && offset < field.End);
}

/// <summary>
/// A site that allocates an array of live objects.
/// </summary>
/// <param name="Caller">The allocation's return address.</param>
/// <param name="Type">The type the site always allocates, for an array the game leaves empty, so that no object holds a type byte to read. <see langword="null"/> reads the type from the first object.</param>
public sealed record LiveArraySite(uint Caller, byte? Type = null);

/// <summary>
/// The live object types, the sites that allocate their arrays, and where their objects' assets are.
/// </summary>
/// <param name="Types">Every type, static and dynamic.</param>
/// <param name="Sites">The sites of the live object arrays.</param>
/// <param name="BootArchives">The archives the game loads once at boot, below every scene, named as a recording names an archive. A scene's objects whose assets aren't in its own archives have them here.</param>
public sealed record LiveLayouts(IReadOnlyList<LiveType> Types, IReadOnlyList<LiveArraySite> Sites, IReadOnlyList<string> BootArchives)
{
    private readonly Dictionary<byte, LiveType> byId = Types.ToDictionary(static type => type.Id);

    /// <summary>
    /// Finds a type by its type byte.
    /// </summary>
    /// <param name="id">The type byte.</param>
    /// <returns>The type, or <see langword="null"/> when no table has it.</returns>
    public LiveType? Find(byte id) => byId.GetValueOrDefault(id);

    /// <summary>
    /// The Xbox layouts (2.4): the static type table at <c>0x2B6AA0</c>, the dynamic kinds ending at <c>0x29784C</c>,
    /// the fields the executable confirms, and the array sites: the scene's own five, the MovePoints' and the surfaces'.
    /// </summary>
    public static LiveLayouts Xbox { get; } = BuildXbox();

    private static LiveLayouts BuildXbox()
    {
        LiveField[] header =
        [
            new("vtable", 0x0, 4),
            new("id", 0x4, 4),
            new("baseType", 0x8, 1),
            new("linkCount", 0x9, 1),
            new("baseFlags", 0xA, 2),
            new("links", 0xC, 4),
            new("eventHandler", 0x10, 4),
        ];
        LiveField[] @base = [.. header, new("asset", 0x14, 4)];
        LiveField[] entity =
        [
            .. @base,
            new("flags", 0x1A, 1),
            new("pflags", 0x1D, 1),
            new("moreFlags", 0x1E, 1),
            new("visUpdate", 0x28, 4),
            new("model", 0x2C, 4),
            new("update", 0x38, 4),
            new("move", 0x44, 4),
            new("frame", 0x4C, 4),
            new("gridb", 0x54, 0xC),
            new("gridb.grid", 0x60, 4),
            new("gridb.head", 0x64, 4),
            new("gridb.next", 0x68, 4),
            new("bound.type", 0x8C, 1),
            new("bound.mat", 0xB4, 4),
            new("transl", 0xB8, 4),
            new("ffx", 0xBC, 4),
            new("driver", 0xC0, 4),
            new("driven", 0xC4, 4),
            new("simpShadow", 0xCC, 4),
            new("atbl", 0xDC, 4),
        ];
        LiveField[] ui = [.. @base, new("behaviour", 0x54, 4), new("motion", 0x60, 4), new("motionTime", 0x64, 4)];

        LiveType[] types =
        [
            new(0x01, "TRIG", 0x1C0, [.. entity, new("box", 0xE0, 0x18)]),
            new(0x03, "PLYR", 0xE0, entity),
            new(0x04, "PKUP", 0x2B0, [.. entity, new("state", 0x2A4, 4), new("pickupFlags", 0x2AC, 4)]),
            new(0x05, "ENV", 0x18, @base),
            new(0x06, "PLAT", 0x2C0, Sorted(
            [
                .. entity,
                new("platform.type", 0x1C, 1),
                new("motion.kind", 0xF4, 1),
                new("mech.rotptr", 0x1AC, 4),
                new("drv.odriver", 0x1FC, 4),
                new("drv.driver", 0x200, 4),
            ])),
            new(0x07, "CAM", 0x18, @base),
            new(0x0B, "SIMP", 0x104, [.. entity, new("sasset", 0xE0, 4), new("sflags", 0xE4, 4), new("anim", 0xF4, 4)]),
            new(0x0D, "MVPT", 0x34, @base),
            new(0x0E, "TIMR", 0x20, @base),
            new(0x10, "PORT", 0x18, @base),
            new(0x11, "GRUP", 0x24, [.. @base, new("items", 0x18, 4), new("last_index", 0x1C, 4), new("flg_group", 0x20, 4)]),
            new(0x12, "PEND", 0x1C0, @base),
            new(0x16, "CNTR", 0x1C, [.. @base, new("count", 0x18, 2), new("state", 0x1A, 1)]),
            new(0x17, "HANG", 0x134, @base),
            new(0x18, "BUTN", 0x1F0, @base),
            new(0x1A, "SURF", 0x2C, @base),
            new(0x1C, "hud:image", 0xC4, ui),
            new(0x1D, "VOLU", 0x18, @base),
            new(0x1F, "COND", 0x1C, @base),
            new(0x24, "FOG", 0x18, @base),
            new(0x25, "LITE", 0x68, @base),
            new(0x26, "PARE", 0x94, @base),
            new(0x27, "PARS", 0x30, @base),
            new(0x28, "CSNM", 0x28, @base),
            new(0x29, "EGEN", 0x120, @base),
            new(0x2A, "SCRP", 0x28, [.. @base, new("nextEvent", 0x18, 4), new("running", 0x1C, 4), new("clock", 0x20, 4), new("speed", 0x24, 4)]),
            new(0x2F, "BOUL", 0x20C, @base),
            new(0x31, "Teleport", 0x14C, @base),
            new(0x32, "BusStop", 0x34, @base),
            new(0x33, "text_box", 0xE0,
            [
                .. header,
                new("flags", 0x14, 1),
                new("padding", 0x15, 3),
                new("asset", 0x18, 4),
                new("tb.context", 0x74, 4),
                new("next", 0xD4, 4),
                new("prev", 0xD8, 4),
                new("bgtex", 0xDC, 4),
            ]),
            new(0x34, "talk_box", 0x44, @base),
            new(0x35, "task_box", 0x2C,
            [
                .. header,
                new("active", 0x14, 4),
                new("asset", 0x1C, 4),
                new("state", 0x20, 4),
                new("talkBox", 0x24, 4),
                new("current", 0x28, 4),
            ]),
            new(0x36, "BoulderGenerator", 0x5C, @base),
            new(0x38, "DSCO", 0x68, @base),
            new(0x3A, "hud:model", 0xAC, ui),
            new(0x3B, "hud:meter:font", 0x164, ui),
            new(0x3C, "hud:meter:unit", 0x1A0, ui),
            new(0x3D, "bungee_hook", 0x1C, @base),
            new(0x3E, "Flythrough", 0x18, @base),
            new(0x3F, "TRCK", 0x104, @base),
            new(0x45, "Camera_Tweak", 0x18, @base),
            new(0x47, "hud:text", 0x190, ui),
            new(0x48, "logic:reference", 0x18, @base),
            new(0x4B, "SDFX", 0x20, @base),
            new(0x4E, "flame_emitter", 0x80, @base),
            new(0x50, "ui:text", 0x74, ui),
            new(0x51, "ui:image", 0x94, ui),
            new(0x52, "ui:model", 0x78, ui),
            new(0x57, "ui:box", 0x100, ui),
            new(0x5A, "ui:text:user string", 0x80, ui),
            new(0x5B, "Rumble", 0x18, @base),
            new(0x5C, "Rumble Spherical Emitter", 0x20, @base),
            new(0x5D, "Rumble Box Emitter", 0x1C, @base),
            new(0x61, "ui:list", 0x80, ui),
            new(0x65, "Lightning", 0x1C, @base),
            new(0x69, "smoke_emitter", 0xA0, @base),
            new(0x6A, "VentType", 0x24, @base),
            new(0x6B, "Vent", 0x270, @base),
            new(0x6D, "RaceTimer", 0x40, @base),
            new(0x6E, "ScreenFade", 0x2C, @base),
            new(0x71, "RingControl", 0x384, [.. @base, new("ringCount", 0x24, 4), new("activeRing", 0x28, 4), new("rings", 0x30, 200 * 4)]),
            new(0x72, "Ring", 0xB0, @base),
            new(0x74, "water_body", 0x34, @base),
            new(0x78, "spotlight", 0xE0, @base),
            new(0x7B, "ui:controller", 0x6C, ui),
            new(0x7D, "JSP Extra Data", 0x14, header),
            new(0x86, "Function Generator", 0x30, @base),
        ];

        return new LiveLayouts(types, [new(0x68E71), new(0x68F3B), new(0x68D28), new(0x69081, 0x03), new(0x6913B), new(0x4577C), new(0x1A05D5)], ["boot", @"MN\mnuc"]);
    }

    private static LiveField[] Sorted(LiveField[] fields) => [.. fields.OrderBy(static field => field.Offset)];
}
