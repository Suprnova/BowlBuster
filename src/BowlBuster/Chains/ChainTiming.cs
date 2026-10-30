using BowlBuster.Loads;

namespace BowlBuster.Chains;

/// <summary>
/// Where a chain that starts at <c>[load]</c> puts its origin and its target.
/// </summary>
/// <param name="Origin">The load the origin is on.</param>
/// <param name="Target">The load the target is on.</param>
/// <param name="K">The number of loads from the origin to the target.</param>
public sealed record ChainTiming(LoadNumber Origin, LoadNumber Target, int K)
{
    /// <summary>
    /// The target's phase, which is what a chain is named by.
    /// </summary>
    public Phase TargetPhase => Target.Phase;
}
