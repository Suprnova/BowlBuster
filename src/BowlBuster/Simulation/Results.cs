using BowlBuster.Loads;
using BowlBuster.Recordings;

namespace BowlBuster.Simulation;

/// <summary>
/// What simulating a chain gave. A chain is either refused, simulated in full, or stopped when the heap ran out.
/// </summary>
/// <param name="Loads">The loads simulated, in order.</param>
/// <param name="Missing">The recordings the chain needs and lacks. When there are any, nothing was simulated.</param>
/// <param name="Exhausted">Where the heap ran out, if it did. <paramref name="Loads"/> holds the loads before that one.</param>
public sealed record ChainResult(IReadOnlyList<SimulatedLoad> Loads, IReadOnlyList<CaptureRequest> Missing, HeapExhaustion? Exhausted)
{
    /// <summary>
    /// Whether every load of the chain was simulated.
    /// </summary>
    public bool IsComplete => Missing.Count is 0 && Exhausted is null;
}

/// <summary>
/// A chain simulated with its target on one phase.
/// </summary>
/// <param name="TargetPhase">The target's phase.</param>
/// <param name="OriginLoad">The load the origin was on, or <see langword="null"/> when the origin has no recording at all.</param>
/// <param name="Result">The simulation.</param>
public sealed record PhaseResult(Phase TargetPhase, LoadNumber? OriginLoad, ChainResult Result);

/// <summary>
/// One load of a simulated chain.
/// </summary>
/// <param name="Position">The load's index in the chain.</param>
/// <param name="Load">The load's number.</param>
/// <param name="Source">The recorded load that was replayed for it.</param>
/// <param name="Status">What the stale write did at this load.</param>
/// <param name="Sphere">The sphere pointer in force once the load has run, if any load has set one.</param>
public sealed record SimulatedLoad(int Position, LoadNumber Load, LoadSource Source, LoadStatus Status, SphereAssignment? Sphere);

/// <summary>
/// What the stale write did at a load.
/// </summary>
public enum LoadStatus
{
    /// <summary>
    /// No load has set the sphere pointer yet, so nothing was written.
    /// </summary>
    BeforeSphere,

    /// <summary>
    /// The load set the sphere pointer. It writes through its own fresh pointer, so it has no landing.
    /// </summary>
    SetsSphere,

    /// <summary>
    /// The player render never reached the write in this load, so it has no landing.
    /// </summary>
    NoCutoff,

    /// <summary>
    /// The load wrote through a pointer an earlier load set.
    /// </summary>
    Landed,
}

/// <summary>
/// The value of the sphere pointer.
/// </summary>
/// <param name="Position">The position of the load that set it.</param>
/// <param name="Address">The sphere instance's simulated address.</param>
public readonly record struct SphereAssignment(int Position, uint Address);

/// <summary>
/// A recording a chain needs: its load has none, or only one later than the chain can use.
/// </summary>
/// <param name="Key">The scene and costumes to record.</param>
/// <param name="Load">The load to record it at or before, or <see langword="null"/> when any load will do.</param>
public readonly record struct CaptureRequest(LoadKey Key, LoadNumber? Load);

/// <summary>
/// Where a chain's heap ran out: a request that succeeded in its recording failed in the simulation.
/// </summary>
/// <param name="Position">The load's position in the chain.</param>
/// <param name="Op">The request's position in the load.</param>
public readonly record struct HeapExhaustion(int Position, int Op);
