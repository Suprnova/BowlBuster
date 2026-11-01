using BowlBuster.Loads;

namespace BowlBuster.Recordings;

/// <summary>
/// One load of a recording.
/// </summary>
/// <param name="Key">What identifies the load across recordings.</param>
/// <param name="Counter">The scene counter as the game held it.</param>
/// <param name="Load">The load's number, or <see langword="null"/> when the counter is at or below the boot scene's, which is not a load.</param>
/// <param name="Heap">What the load did to the heap, which is what replay runs.</param>
public sealed record RecordedLoad(LoadKey Key, int Counter, LoadNumber? Load, HeapLog Heap);
