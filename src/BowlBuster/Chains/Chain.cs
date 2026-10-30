namespace BowlBuster.Chains;

/// <summary>
/// A sequence of loads that carries a Bowl Storage write from an origin to a target: the origin, which sets the bowl's
/// pointer, any filler loads, and the target.
/// </summary>
/// <remarks>
/// A chain either starts at <c>[load]</c>, the file load, with burns before its origin, or is a shape that says nothing
/// about the loads before the origin. The level straight after <c>[load]</c> or the burns is the origin. Only a shape
/// carries the phases its target may be on, because a chain that starts at <c>[load]</c> has a fixed target phase.
/// </remarks>
public sealed class Chain
{
    /// <summary>
    /// Creates a chain.
    /// </summary>
    /// <param name="burns">The number of loads between <c>[load]</c> and the origin, or <see langword="null"/> for a shape.</param>
    /// <param name="origin">The origin.</param>
    /// <param name="fillers">The runs of filler loads between the origin and the target.</param>
    /// <param name="target">The target.</param>
    /// <param name="targetPhases">The phases the target may be on, for a shape.</param>
    /// <exception cref="ArgumentOutOfRangeException"><paramref name="burns"/> is negative.</exception>
    /// <exception cref="ArgumentException"><paramref name="burns"/> and <paramref name="targetPhases"/> are both given.</exception>
    public Chain(int? burns, LevelStep origin, IEnumerable<FillerStep> fillers, LevelStep target, PhaseSet? targetPhases = null)
    {
        ArgumentNullException.ThrowIfNull(origin);
        ArgumentNullException.ThrowIfNull(fillers);
        ArgumentNullException.ThrowIfNull(target);

        if (burns is { } count) ArgumentOutOfRangeException.ThrowIfNegative(count);

        if (burns is not null && targetPhases is not null)
            throw new ArgumentException("A chain that starts at [load] has a fixed target phase.", nameof(targetPhases));

        Burns = burns;
        Origin = origin;
        Fillers = [.. fillers];
        Target = target;
        TargetPhases = targetPhases;
    }

    /// <summary>
    /// The number of loads between <c>[load]</c> and the origin, or <see langword="null"/> for a shape.
    /// </summary>
    public int? Burns { get; }

    /// <summary>
    /// Whether the chain starts at <c>[load]</c>, so that its loads are numbered.
    /// </summary>
    public bool IsFull => Burns is not null;

    /// <summary>
    /// The origin.
    /// </summary>
    public LevelStep Origin { get; }

    /// <summary>
    /// The runs of filler loads between the origin and the target.
    /// </summary>
    public IReadOnlyList<FillerStep> Fillers { get; }

    /// <summary>
    /// The target.
    /// </summary>
    public LevelStep Target { get; }

    /// <summary>
    /// The phases the target may be on, for a shape; <see langword="null"/> when unwritten or for a chain that starts at <c>[load]</c>.
    /// </summary>
    public PhaseSet? TargetPhases { get; }

    /// <summary>
    /// The number of loads from the origin to the target.
    /// </summary>
    public int K => Fillers.Sum(static filler => filler.Count) + 1;

    /// <summary>
    /// Where the chain puts its origin and target, or <see langword="null"/> for a shape.
    /// </summary>
    public ChainTiming? Timing => Burns is { } burns
        ? new ChainTiming(new LoadNumber(burns + 2), new LoadNumber(burns + 2 + K), K)
        : null;

    /// <summary>
    /// The phases the origin must land on. For a chain that starts at <c>[load]</c> that is the phase of its origin; for a
    /// shape it is the phase each of <see cref="TargetPhases"/> needs, <see cref="K"/> loads earlier, or all four
    /// when the target's phases are unwritten.
    /// </summary>
    public PhaseSet OriginPhases => Timing is { } timing
        ? new PhaseSet(timing.Origin.Phase)
        : new PhaseSet([.. (TargetPhases ?? PhaseSet.All).Phases.Select(phase => Earlier(phase, K))]);

    /// <summary>
    /// Numbers the loads of a chain that starts at <c>[load]</c>: <c>[load]</c> is load 1, then the burns, the origin,
    /// each run of fillers and the target.
    /// </summary>
    /// <returns>Each step with the loads it fills, in order.</returns>
    /// <exception cref="InvalidOperationException">The chain is a shape, which has no numbered loads.</exception>
    public IReadOnlyList<PlacedStep> NumberLoads()
    {
        int burns = Burns ?? throw new InvalidOperationException("Only a chain that starts at [load] has numbered loads.");
        List<PlacedStep> steps = [];
        int next = 1;

        Place("[load]", 1);
        if (burns > 0) Place($"burn x{burns}", burns);

        Place(Origin.ToString(), 1);
        foreach (FillerStep filler in Fillers)
        {
            Place(filler.ToString(), filler.Count);
        }

        Place(Target.ToString(), 1);
        return steps;

        void Place(string text, int count)
        {
            steps.Add(new PlacedStep(text, new LoadNumber(next), new LoadNumber(next + count - 1)));
            next += count;
        }
    }

    /// <summary>
    /// Prints the chain as runners write it: steps joined by " &gt; ", beginning with <c>[load]</c> and <c>burn xN</c>
    /// for a full chain, and ending with <c>[target: 4th or 1st]</c> for a shape with target phases.
    /// </summary>
    /// <returns>The chain.</returns>
    public override string ToString()
    {
        string[] prefix = Burns switch
        {
            null => [],
            0 => ["[load]"],
            { } burns => ["[load]", $"burn x{burns}"],
        };
        string[] steps = [.. prefix, Origin.ToString(), .. Fillers.Select(static filler => filler.ToString()), Target.ToString()];
        string text = string.Join(" > ", steps);
        return TargetPhases is { } phases ? $"{text} [target: {phases}]" : text;
    }

    private static Phase Earlier(Phase phase, int loads)
    {
        int residue = (((int)phase % 4) - loads) % 4;
        residue = (residue + 4) % 4;
        return (Phase)(residue is 0 ? 4 : residue);
    }
}
