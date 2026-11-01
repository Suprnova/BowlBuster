namespace BowlBuster.Platforms;

/// <summary>
/// The size of one model pool, which a scene creates when it starts.
/// </summary>
/// <param name="Count">The number of model instances in the pool.</param>
/// <param name="Matrices">The number of bone matrices each instance has.</param>
public readonly record struct ModelPoolShape(int Count, int Matrices);
