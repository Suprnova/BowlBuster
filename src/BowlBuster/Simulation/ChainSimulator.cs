using BowlBuster.Chains;
using BowlBuster.Landings;
using BowlBuster.Loads;
using BowlBuster.Memory;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Replay;

namespace BowlBuster.Simulation;

/// <summary>
/// Simulates chains by replaying each load's recorded requests on one heap, from the first load's recorded start state.
/// </summary>
/// <remarks>
/// A load running later than its recording is reached by extra leaks, one per load, since a leak is all a load leaves
/// behind. Whether a load sets the sphere comes from its recording alone: the requests either hold the allocation or
/// they don't. A chain's named origin isn't checked against this, so a filler that sets the sphere simply takes over.
/// </remarks>
/// <param name="profile">The platform's constants.</param>
/// <param name="library">The recordings to draw on.</param>
public sealed class ChainSimulator(PlatformProfile profile, RecordingLibrary library)
{
    /// <summary>
    /// Simulates a chain.
    /// </summary>
    /// <param name="plan">The loads to simulate.</param>
    /// <returns>A result per load, or the recordings the plan lacks.</returns>
    /// <exception cref="ArgumentException"><paramref name="plan"/> has no loads.</exception>
    /// <exception cref="InvalidOperationException">A recorded load started at another heap depth from the load before it. Every validated load starts at the leak's depth.</exception>
    public ChainResult Simulate(ChainPlan plan)
    {
        ArgumentNullException.ThrowIfNull(plan);
        if (plan.Loads.Count is 0) throw new ArgumentException("A plan has at least one load.", nameof(plan));

        LoadSource?[] sources = [.. plan.Loads.Select((key, position) => Select(key, LoadAt(plan, position), position))];
        CaptureRequest[] missing =
        [
            .. plan.Loads
                .Select((key, position) => (Key: key, Position: position))
                .Where(load => sources[load.Position] is null)
                .Select(load => new CaptureRequest(load.Key, LoadAt(plan, load.Position))),
        ];

        return missing.Length > 0
            ? new ChainResult([], missing, null)
            : Replay(plan, [.. sources.OfType<LoadSource>()]);
    }

    /// <summary>
    /// Simulates a shape on each phase it allows, from the earliest origin load that puts its target there.
    /// </summary>
    /// <param name="shape">The shape, with the phases its target may be on, or all four when it names none.</param>
    /// <param name="sceneOf">Maps a level as the shape writes it to its scene.</param>
    /// <returns>A result per phase, in phase order.</returns>
    /// <exception cref="ArgumentException"><paramref name="shape"/> starts at <c>[load]</c>, which fixes its phase, or a filler names no level.</exception>
    public IReadOnlyList<PhaseResult> SimulatePhases(Chain shape, Func<string, string> sceneOf)
    {
        ArgumentNullException.ThrowIfNull(shape);
        if (shape.IsFull) throw new ArgumentException("A chain that starts at [load] has one phase.", nameof(shape));

        ChainPlan plan = ChainPlan.From(shape, sceneOf, new LoadNumber(1));
        LoadKey origin = plan.Loads[0];
        IReadOnlyList<LoadSource> origins = library.Find(origin);

        return [.. (shape.TargetPhases ?? PhaseSet.All).Phases.Select(phase => origins.Count is 0
            ? new PhaseResult(phase, null, new ChainResult([], [new CaptureRequest(origin, null)], null))
            : Simulate(phase, plan with { FirstLoad = FirstOnPhase(origins[0].Number, shape.K, phase) }))];
    }

    private static LoadNumber LoadAt(ChainPlan plan, int position) => new(plan.FirstLoad.Value + position);

    private static LoadNumber FirstOnPhase(LoadNumber earliest, int k, Phase phase) => new(Enumerable
        .Range(earliest.Value, 4)
        .First(load => new LoadNumber(load + k).Phase == phase));

    private PhaseResult Simulate(Phase phase, ChainPlan plan) => new(phase, plan.FirstLoad, Simulate(plan));

    private LoadSource? Select(LoadKey key, LoadNumber load, int position)
    {
        IReadOnlyList<LoadSource> candidates = library.Find(key);

        return candidates.LastOrDefault(candidate => candidate.Number.Value <= load.Value)
            ?? (position > 0 && candidates.Count > 0 ? candidates[0] : null);
    }

    private ChainResult Replay(ChainPlan plan, LoadSource[] sources)
    {
        GameHeap heap = sources[0].Load.Heap.Start.ToHeap(profile.Heap0);
        for (int leak = sources[0].Number.Value; leak < plan.FirstLoad.Value; leak++)
        {
            heap.Allocate(profile.PlayerEntitySize, 0);
        }

        BlockTracker tracker = new(profile.Heap0);
        List<SimulatedLoad> loads = [];
        SphereAssignment? sphere = null;

        for (int position = 0; position < sources.Length; position++)
        {
            HeapLog log = sources[position].Load.Heap;
            int depth = heap.Depth;

            if (depth != log.Start.Depth)
                throw new InvalidOperationException($"A load that starts at depth {log.Start.Depth} can't follow one that ended at depth {depth}.");

            bool setsSphere = log.Requests.Any(IsSphere);
            HeapReplayer replayer = new(profile, heap);
            Landing? landing = null;
            tracker.BeginLoad();

            for (int op = 0; op <= log.Requests.Count; op++)
            {
                if (op == log.Cutoff?.RequestCount && !setsSphere && sphere is { } stale)
                    landing = Resolve(stale, tracker, heap);

                if (op == log.Requests.Count) break;

                uint? result = tracker.Apply(replayer, op, log.Requests[op]);

                if (result is 0) return new ChainResult(loads, [], new HeapExhaustion(position, op));
                if (result is { } instance && IsSphere(log.Requests[op])) sphere = new SphereAssignment(position, instance);
            }

            tracker.PopTo(heap, depth);

            LoadStatus status = setsSphere ? LoadStatus.SetsSphere
                : sphere is null ? LoadStatus.BeforeSphere
                : log.Cutoff is null ? LoadStatus.NoCutoff
                : LoadStatus.Landed;

            loads.Add(new SimulatedLoad(position, LoadAt(plan, position), sources[position], status, sphere, landing));
        }

        return new ChainResult(loads, [], null);
    }

    private Landing Resolve(SphereAssignment sphere, BlockTracker tracker, GameHeap heap) => new(
        sphere,
        tracker.FindFrom(profile.Sites.PlayerEntity)?.Address,
        new LandingHeap(tracker.HeapTop, heap.Current.Cursor, heap.Depth),
        [.. profile.Footprint.Words.Select(word => Resolve(word, sphere, tracker))]);

    private static LandingWord Resolve(FootprintWord word, SphereAssignment sphere, BlockTracker tracker)
    {
        uint address = sphere.Address + word.Offset;
        return new LandingWord(word, address, tracker.Locate(address, sphere.Position), null, false);
    }

    private bool IsSphere(HeapRequest request) => request is PoolAllocRequest instance && instance.Caller == profile.Sites.Sphere;
}
