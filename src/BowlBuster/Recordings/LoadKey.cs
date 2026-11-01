using BowlBuster.Chains;

namespace BowlBuster.Recordings;

/// <summary>
/// What identifies a load across recordings: the scene and the costumes worn. Together they decide which player archives
/// load, and so the requests the load makes.
/// </summary>
/// <param name="Scene">The scene.</param>
/// <param name="Costumes">The costumes worn, which are <see cref="Chains.Costumes.None"/> when none is equipped.</param>
public readonly record struct LoadKey(string Scene, Costumes Costumes);
