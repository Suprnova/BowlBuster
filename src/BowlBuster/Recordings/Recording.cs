using BowlBuster.Loads;

namespace BowlBuster.Recordings;

/// <summary>
/// One run of the game, load by load, as the harness recorded it.
/// </summary>
/// <param name="Id">The run's identity.</param>
/// <param name="Platform">The platform the run was recorded on. A recording never stands in for a load on another platform.</param>
/// <param name="Basis">How the run's scene counters map to load numbers.</param>
/// <param name="EventsDropped">The number of events the harness lost. A lost event can hide a request or a cutoff.</param>
/// <param name="Segments">The run's unbroken stretches, in order.</param>
public sealed record Recording(string Id, string Platform, CounterBasis Basis, int EventsDropped, IReadOnlyList<RecordingSegment> Segments);
