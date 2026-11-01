using BowlBuster.Loads;
using BowlBuster.Recordings;
using BowlBuster.Replay;

namespace BowlBuster.Simulation;

/// <summary>
/// Every load a chain can draw on: the numbered loads with requests, from recordings that passed validation.
/// </summary>
/// <remarks>
/// The boot scene isn't a load, so it can't be part of a chain, and a load with no requests has nothing to replay.
/// </remarks>
/// <param name="recordings">The recordings.</param>
public sealed class RecordingLibrary(IEnumerable<ValidatedRecording> recordings)
{
    private readonly Dictionary<LoadKey, LoadSource[]> sources = recordings
        .SelectMany(static validated => validated.Recording.Segments.SelectMany(segment => segment.Loads
            .Where(static load => load.Load is not null && load.Heap.Requests.Count > 0)
            .Select(load => new LoadSource(validated.Recording.Id, segment.Index, load))))
        .OrderBy(static source => source.Number.Value)
        .ThenBy(static source => source.RecordingId, StringComparer.Ordinal)
        .ThenBy(static source => source.Segment)
        .GroupBy(static source => source.Load.Key)
        .ToDictionary(static group => group.Key, static group => group.ToArray());

    /// <summary>
    /// Finds the recorded loads of a key.
    /// </summary>
    /// <param name="key">The key.</param>
    /// <returns>Every load with that key, ordered by load number, then recording, then segment, so that a choice among them is repeatable.</returns>
    public IReadOnlyList<LoadSource> Find(LoadKey key) => sources.GetValueOrDefault(key) ?? [];
}

/// <summary>
/// A recorded load and where it came from.
/// </summary>
/// <param name="RecordingId">The recording's <see cref="Recording.Id"/>.</param>
/// <param name="Segment">The segment's number in the recording.</param>
/// <param name="Load">The load, which has a load number.</param>
public sealed record LoadSource(string RecordingId, int Segment, RecordedLoad Load)
{
    /// <summary>
    /// The load's number in its recording.
    /// </summary>
    public LoadNumber Number => Load.Load!.Value;
}
