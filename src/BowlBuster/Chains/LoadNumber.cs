namespace BowlBuster.Chains;

/// <summary>
/// A load, numbered as runners number them: the first scene after the main menu at boot is load 1. This is the only
/// number BowlBuster shows for a load.
/// </summary>
/// <remarks>
/// Every scene initialisation is a load, including a pause-menu warp, a level-end transition, a new game's first scene,
/// loading a save and quitting to the main menu. Booting to the main menu is not a load, and neither is a death or a
/// reset.
/// </remarks>
public readonly record struct LoadNumber
{
    /// <summary>
    /// Creates a load number.
    /// </summary>
    /// <param name="value">The load's number, 1 or more.</param>
    /// <exception cref="ArgumentOutOfRangeException"><paramref name="value"/> is below 1.</exception>
    public LoadNumber(int value)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(value, 1);
        Value = value;
    }

    /// <summary>
    /// The load's number, 1 or more.
    /// </summary>
    public int Value { get; }

    /// <summary>
    /// The load's phase: its number modulo 4, which the layout of the heap repeats with.
    /// </summary>
    public Phase Phase => (Phase)(Value % 4 is 0 ? 4 : Value % 4);

    /// <inheritdoc/>
    public override string ToString() => $"load {Value}";
}
