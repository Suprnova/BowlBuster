using BowlBuster.Loads;

namespace BowlBuster.Chains;

/// <summary>
/// A step of a chain that starts at <c>[load]</c>, with the loads it fills.
/// </summary>
/// <param name="Text">The step as it is written in the chain.</param>
/// <param name="First">The first load the step fills.</param>
/// <param name="Last">The last load the step fills, which is <paramref name="First"/> for a single load.</param>
public sealed record PlacedStep(string Text, LoadNumber First, LoadNumber Last);
