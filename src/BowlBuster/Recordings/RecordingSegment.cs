namespace BowlBuster.Recordings;

/// <summary>
/// An unbroken stretch of a recording. A new one starts at each resume from a saved state, so counters repeat between
/// segments and a load is only found within its own.
/// </summary>
/// <param name="Index">The segment's number in the recording.</param>
/// <param name="Loads">The loads in order. A resume can start partway through a load; that load's requests have no start state, so it isn't here.</param>
public sealed record RecordingSegment(int Index, IReadOnlyList<RecordedLoad> Loads);
