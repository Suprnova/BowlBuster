namespace BowlBuster.Chains;

/// <summary>
/// How a recording's scene counter maps to load numbers: the scene the game boots into and the counter value it has.
/// </summary>
/// <remarks>
/// The game counts scenes from its boot scene and never reads the counter. A recording stores the counter exactly as the
/// game held it, with its basis, and converts to <see cref="LoadNumber"/> at the boundary. The same position in a chain
/// has a different counter on a disc that boots elsewhere, so counters are never compared across bases.
/// </remarks>
/// <param name="BootScene">The scene the game boots into.</param>
/// <param name="BootCounter">The counter the boot scene has. It is not a load.</param>
public sealed record CounterBasis(string BootScene, int BootCounter)
{
    /// <summary>
    /// The retail disc, which boots into the main menu with the counter at 1.
    /// </summary>
    public static CounterBasis Retail { get; } = new("MNUS", 1);

    /// <summary>
    /// Converts a scene counter to the load that holds it.
    /// </summary>
    /// <param name="counter">The counter as the game held it.</param>
    /// <returns>The load number, which is the counter less <see cref="BootCounter"/>.</returns>
    /// <exception cref="ArgumentOutOfRangeException"><paramref name="counter"/> is the boot scene's counter or below it, which is not a load.</exception>
    public LoadNumber ToLoad(int counter)
    {
        ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(counter, BootCounter);
        return new LoadNumber(counter - BootCounter);
    }

    /// <summary>
    /// Converts a load to the scene counter it has on this basis.
    /// </summary>
    /// <param name="load">The load.</param>
    /// <returns>The counter as the game holds it.</returns>
    public int ToCounter(LoadNumber load) => load.Value + BootCounter;
}
