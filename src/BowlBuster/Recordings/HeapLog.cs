using BowlBuster.Memory;

namespace BowlBuster.Recordings;

/// <summary>
/// What one load did to the heap: the state it started from and every request it made.
/// </summary>
/// <param name="Start">The heap when the scene started.</param>
/// <param name="Requests">The requests in order, up to the next scene's start. The exit's pops are among them.</param>
/// <param name="Cutoff">Where the stale write first happened, or <see langword="null"/> when it never did, which leaves the load with no landing.</param>
/// <param name="ReachedExit">Whether the recording reached the scene's exit, and so holds its pops.</param>
public sealed record HeapLog(HeapSnapshot Start, IReadOnlyList<HeapRequest> Requests, Cutoff? Cutoff, bool ReachedExit);

/// <summary>
/// The first frame the player render reached the stale write in a load. A landing is resolved against the heap as it
/// stood here, not as the load left it.
/// </summary>
/// <param name="RequestCount">The number of requests made before it.</param>
/// <param name="CaptureId">The capture taken here, if one was kept.</param>
public readonly record struct Cutoff(int RequestCount, string? CaptureId);
