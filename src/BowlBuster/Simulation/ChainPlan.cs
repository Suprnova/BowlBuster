using BowlBuster.Chains;
using BowlBuster.Loads;
using BowlBuster.Recordings;

namespace BowlBuster.Simulation;

/// <summary>
/// The loads to simulate, one key per load in order. Unlike a <see cref="Chain"/>, which is how runners write a chain,
/// a plan names every load, with the costumes it wears.
/// </summary>
/// <param name="FirstLoad">The load number of the first load.</param>
/// <param name="Loads">The loads, consecutive from <paramref name="FirstLoad"/>.</param>
public sealed record ChainPlan(LoadNumber FirstLoad, IReadOnlyList<LoadKey> Loads)
{
    /// <summary>
    /// Plans the loads of a chain from its origin on. The loads before the origin aren't simulated: the load number stands
    /// for them, because all they do is leak.
    /// </summary>
    /// <param name="chain">The chain. Every filler must name its level.</param>
    /// <param name="sceneOf">Maps a level as the chain writes it to its scene.</param>
    /// <param name="originLoad">The origin's load, for a shape. A chain that starts at <c>[load]</c> has its own.</param>
    /// <returns>The plan. A filler wears no costume, since the notation gives it none.</returns>
    /// <exception cref="ArgumentException">A filler names no level, or a shape has no <paramref name="originLoad"/>.</exception>
    public static ChainPlan From(Chain chain, Func<string, string> sceneOf, LoadNumber? originLoad = null)
    {
        ArgumentNullException.ThrowIfNull(chain);
        ArgumentNullException.ThrowIfNull(sceneOf);

        LoadNumber first = chain.Timing?.Origin ?? originLoad
            ?? throw new ArgumentException("A shape needs the load its origin is on.", nameof(originLoad));

        return new ChainPlan(
            first,
            [Key(chain.Origin), .. chain.Fillers.SelectMany(Keys), Key(chain.Target)]);

        LoadKey Key(LevelStep step) => new(sceneOf(step.Level), step.Costumes);

        IEnumerable<LoadKey> Keys(FillerStep filler) => filler.Level is { } level
            ? Enumerable.Repeat(new LoadKey(sceneOf(level), Costumes.None), filler.Count)
            : throw new ArgumentException($"'{filler}' names no load, so it can't be simulated.", nameof(chain));
    }
}
