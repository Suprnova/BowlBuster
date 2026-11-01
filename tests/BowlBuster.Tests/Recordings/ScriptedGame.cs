using BowlBuster.Chains;
using BowlBuster.Loads;
using BowlBuster.Memory;
using BowlBuster.Recordings;
using System.Text.Json.Nodes;

namespace BowlBuster.Tests.Recordings;

internal abstract record Step;

internal sealed record Alloc(uint Size, uint Alignment, uint Caller, LayerId? Layer = null) : Step;

internal sealed record Grow(uint Size) : Step;

internal sealed record Push : Step;

internal sealed record PopTo(int Depth) : Step;

internal sealed record Pool(int NodeCount, uint Flags, uint Caller) : Step;

internal sealed record FreePoolAlloc(int Index) : Step;

internal sealed record CutoffHere : Step;

internal sealed record ExitScene : Step;

internal sealed record Scene(string Name, Step[] Steps);

/// <summary>
/// Plays scripted scenes and writes down what a harness would have recorded. This is the oracle for every test of a
/// recording, so it calls nothing under test: it places blocks with the placement formula as the game's code has it,
/// and computes pool instances and free lists itself.
/// </summary>
internal sealed class ScriptedGame(HeapSnapshot start, string run = "synthetic-1")
{
    private const uint HeaderAllowance = 12;
    private const uint DefaultAlignment = 16;
    private const uint PoolSite = 0x182B2A;
    private const uint PoolHeader = 0xC;
    private const uint InstanceSize = 0xA0;
    private const uint MatrixSize = 0x40;

    private static readonly (uint Size, int Count, int Matrices)[] PoolKinds = [(72_588, 0x144, 1), (49_740, 0x4A, 8), (208_556, 0x31, 0x40)];

    private readonly List<JsonObject> events = [];
    private readonly JsonArray loadRows = [];
    private readonly SortedDictionary<int, List<RecordedLoad>> segments = [];
    private readonly Dictionary<string, uint> captureTops = [];

    private List<HeapState> states = [.. start.States];
    private HeapBlock? lastBlock = start.LastBlock;
    private int segment;

    public IReadOnlyDictionary<string, uint> CaptureTops => captureTops;

    public uint Cursor => states[^1].Cursor;

    public Recording Recording => new(
        run,
        "xbox",
        new CounterBasis("MNUS", 1),
        0,
        [.. segments.Select(static pair => new RecordingSegment(pair.Key, pair.Value))]);

    public string ManifestText => new JsonObject
    {
        ["schema_version"] = 1,
        ["run"] = run,
        ["disc"] = new JsonObject { ["platform"] = "xbox" },
        ["counter_basis"] = new JsonObject { ["boot_scene"] = "MNUS", ["boot_counter"] = 1 },
        ["events_dropped"] = 0,
        ["loads"] = loadRows.DeepClone(),
    }.ToJsonString();

    public string EventText => string.Join('\n', events.Select(static line => line.ToJsonString()));

    public ScriptedGame BeginSegment(HeapSnapshot resumed)
    {
        segment++;
        states = [.. resumed.States];
        lastBlock = resumed.LastBlock;
        return this;
    }

    public ScriptedGame Run(Scene scene, int counter, Costumes? costumes = null, string? capture = null)
    {
        Costumes worn = costumes ?? Costumes.None;
        LoadPlayer player = new(this, capture);

        Emit("scene_init", new JsonObject
        {
            ["scene"] = scene.Name,
            ["caller"] = 0x52890,
            ["counter"] = counter,
            ["heap"] = HeapObject(),
        });
        HeapSnapshot loadStart = new([.. states], lastBlock);

        foreach (Step step in scene.Steps) player.Play(step);

        RecordedLoad load = new(
            new LoadKey(scene.Name, worn),
            counter,
            counter > 1 ? new LoadNumber(counter - 1) : null,
            new HeapLog(loadStart, player.Requests, player.Cutoff is { } count ? new Cutoff(count, player.Capture) : null, player.ReachedExit));

        if (!segments.TryGetValue(segment, out List<RecordedLoad>? loads)) segments[segment] = loads = [];
        loads.Add(load);

        loadRows.Add(new JsonObject
        {
            ["segment"] = segment,
            ["counter"] = counter,
            ["costumes"] = new JsonObject { ["spongebob"] = worn.Spongebob, ["patrick"] = worn.Patrick },
        });

        return this;
    }

    private static uint AlignUp(uint value, uint alignment) => (value + alignment - 1) & ~(alignment - 1);

    private JsonObject HeapObject()
    {
        JsonArray rows = [];
        foreach (HeapState state in states)
        {
            rows.Add(new JsonObject { ["cursor"] = state.Cursor, ["blocks"] = state.BlockCount, ["used"] = state.Used, ["wasted"] = 0 });
        }

        return new JsonObject
        {
            ["depth"] = states.Count - 1,
            ["states"] = rows,
            ["last_block"] = lastBlock is { } block ? new JsonObject { ["address"] = block.Address, ["size"] = block.Size } : null,
        };
    }

    private void Emit(string name, JsonObject fields)
    {
        fields["seq"] = events.Count + 1;
        fields["segment"] = segment;
        fields["frame"] = 120;
        fields["event"] = name;
        events.Add(fields);
    }

    private void Advance(uint bytes, int blocks)
    {
        HeapState state = states[^1];
        states[^1] = new HeapState(state.Cursor + bytes, state.BlockCount + blocks, state.Used + bytes);
    }

    private sealed class LoadPlayer(ScriptedGame game, string? capture)
    {
        private readonly List<PoolPlay> pools = [];
        private readonly List<uint> poolAllocs = [];

        public List<HeapRequest> Requests { get; } = [];

        public int? Cutoff { get; private set; }

        public string? Capture { get; private set; }

        public bool ReachedExit { get; private set; }

        public void Play(Step step)
        {
            switch (step)
            {
                case Alloc alloc:
                    PlayAlloc(alloc);
                    break;

                case Grow grow:
                    uint rounded = AlignUp(grow.Size, 4);
                    game.Advance(rounded, 0);
                    game.lastBlock = game.lastBlock!.Value with { Size = game.lastBlock.Value.Size + rounded };
                    game.Emit("grow", new JsonObject { ["heap"] = 0, ["size"] = grow.Size });
                    Requests.Add(new GrowRequest(grow.Size));
                    break;

                case Push:
                    game.states.Add(game.states[^1]);
                    game.Emit("push", new JsonObject { ["heap"] = 0 });
                    Requests.Add(new PushRequest());
                    break;

                case PopTo pop:
                    game.states.RemoveRange(pop.Depth + 1, game.states.Count - pop.Depth - 1);
                    game.Emit("pop", new JsonObject { ["heap"] = 0, ["depth"] = pop.Depth });
                    Requests.Add(new PopRequest(pop.Depth));
                    break;

                case Pool pool:
                    PlayPoolAlloc(pool);
                    break;

                case FreePoolAlloc free:
                    PlayFree(poolAllocs[free.Index]);
                    break;

                case CutoffHere:
                    Cutoff = Requests.Count;
                    game.Emit("drawn", []);
                    if (capture is not null)
                    {
                        Capture = capture;
                        game.captureTops[capture] = game.Cursor;
                        game.Emit("capture", new JsonObject { ["id"] = capture, ["trigger"] = "cutoff" });
                    }

                    break;

                case ExitScene:
                    ReachedExit = true;
                    game.Emit("scene_exit", []);
                    break;

                default:
                    throw new ArgumentException($"Unknown step {step}.", nameof(step));
            }
        }

        private void PlayAlloc(Alloc alloc)
        {
            uint address = GameHeap.ZeroSizeAddress;

            if (alloc.Size is not 0)
            {
                uint alignment = Math.Max(alloc.Alignment, DefaultAlignment);
                uint cursor = game.Cursor;
                uint m = (cursor + HeaderAllowance) & (alignment - 1);
                uint pre = HeaderAllowance + ((alignment - m) & (alignment - 1));

                address = cursor + pre;
                game.Advance((pre + alloc.Size + 3) & ~3u, 1);
                game.lastBlock = new HeapBlock(address, alloc.Size);

                if (alloc.Caller is PoolSite)
                {
                    (_, int count, int matrices) = PoolKinds.First(kind => kind.Size == alloc.Size);
                    pools.Add(new PoolPlay(address, count, matrices));
                }
            }

            JsonObject line = new()
            {
                ["heap"] = 0,
                ["size"] = alloc.Size,
                ["alignment"] = alloc.Alignment,
                ["address"] = address,
                ["caller"] = alloc.Caller,
            };

            if (alloc.Layer is { } layer) line["layer"] = new JsonObject { ["archive"] = layer.Archive, ["layer"] = layer.Layer };

            game.Emit("alloc", line);
            Requests.Add(new AllocRequest(alloc.Size, alloc.Alignment, address, alloc.Caller, alloc.Layer));
        }

        private void PlayPoolAlloc(Pool pool)
        {
            int needed = pool.NodeCount + 1 + ((pool.Flags & 0x40) is 0 ? 0 : 1);
            PoolPlay from = pools.Where(candidate => candidate.Matrices >= needed && candidate.Free.Count > 0).OrderBy(static candidate => candidate.Matrices).First();
            uint instance = from.InstanceAddress(from.Free.Pop());

            poolAllocs.Add(instance);
            game.Emit("model", new JsonObject
            {
                ["bypass"] = false,
                ["instance"] = instance,
                ["nodes"] = pool.NodeCount,
                ["flags"] = pool.Flags,
                ["caller"] = pool.Caller,
            });
            Requests.Add(new PoolAllocRequest(instance, pool.Caller, pool.NodeCount, pool.Flags));
        }

        private void PlayFree(uint instance)
        {
            PoolPlay from = pools.First(candidate => Enumerable.Range(0, candidate.Count).Any(index => candidate.InstanceAddress(index) == instance));

            from.Free.Push(Enumerable.Range(0, from.Count).First(index => from.InstanceAddress(index) == instance));
            game.Emit("pool_free", new JsonObject { ["instance"] = instance });
            Requests.Add(new PoolFreeRequest(instance));
        }
    }

    private sealed class PoolPlay(uint block, int count, int matrices)
    {
        public int Count { get; } = count;

        public int Matrices { get; } = matrices;

        public Stack<int> Free { get; } = new(Enumerable.Range(0, count).Reverse());

        public uint InstanceAddress(int index) => block + ((uint)Count * (uint)Matrices * MatrixSize) + PoolHeader + ((uint)index * InstanceSize);
    }
}
