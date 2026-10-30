using System.Globalization;

namespace BowlBuster.Chains;

/// <summary>
/// A set of <see cref="Phase"/>s, such as the phases a chain's target may land on.
/// </summary>
/// <remarks>
/// A set prints its phases in order, as "4th", "1st or 4th" or "1st, 2nd or 3rd", and parses them in any order and
/// wording.
/// </remarks>
public readonly record struct PhaseSet
{
    private static readonly Phase[] AllPhases = [Phase.First, Phase.Second, Phase.Third, Phase.Fourth];

    private readonly byte mask;

    /// <summary>
    /// Creates a set of the given phases.
    /// </summary>
    /// <param name="phases">The phases in the set. Repeats are ignored.</param>
    public PhaseSet(params ReadOnlySpan<Phase> phases)
    {
        foreach (Phase phase in phases)
        {
            mask |= Bit(phase);
        }
    }

    /// <summary>
    /// The set of all four phases.
    /// </summary>
    public static PhaseSet All => new(Phase.First, Phase.Second, Phase.Third, Phase.Fourth);

    /// <summary>
    /// The phases in the set, in order.
    /// </summary>
    public IEnumerable<Phase> Phases => AllPhases.Where(Contains);

    /// <summary>
    /// Whether the set holds <paramref name="phase"/>.
    /// </summary>
    /// <param name="phase">The phase to look for.</param>
    /// <returns><see langword="true"/> when the set holds it.</returns>
    public bool Contains(Phase phase) => (mask & Bit(phase)) is not 0;

    /// <summary>
    /// The name runners give a phase: "1st", "2nd", "3rd" or "4th".
    /// </summary>
    /// <param name="phase">The phase.</param>
    /// <returns>The phase's ordinal.</returns>
    public static string Ordinal(Phase phase) => phase switch
    {
        Phase.First => "1st",
        Phase.Second => "2nd",
        Phase.Third => "3rd",
        Phase.Fourth => "4th",
        _ => ((int)phase).ToString(CultureInfo.InvariantCulture),
    };

    /// <summary>
    /// Parses phases such as "4th or 1st" or "1st, 2nd or 3rd" by reading their digits: every digit must stand alone
    /// and be 1 to 4, and everything else is ignored.
    /// </summary>
    /// <param name="text">The text to parse.</param>
    /// <returns>The set.</returns>
    /// <exception cref="FormatException"><paramref name="text"/> has no digits, a digit outside 1 to 4, or a number of more than one digit such as "11th".</exception>
    public static PhaseSet Parse(string text) =>
        TryParse(text, out PhaseSet set) ? set : throw new FormatException($"'{text}' is not a list of phases such as '4th or 1st'.");

    /// <summary>
    /// Tries to parse phases such as "4th or 1st". See <see cref="Parse"/>.
    /// </summary>
    /// <param name="text">The text to parse.</param>
    /// <param name="set">The set, when parsing succeeds.</param>
    /// <returns><see langword="true"/> when <paramref name="text"/> is a list of phases.</returns>
    public static bool TryParse(string? text, out PhaseSet set)
    {
        set = default;
        char[] digits = [.. text?.Where(char.IsAsciiDigit) ?? []];
        bool hasMultiDigitNumber = text?.Zip(text.Skip(1)).Any(pair => char.IsAsciiDigit(pair.First) && char.IsAsciiDigit(pair.Second)) ?? false;
        if (digits.Length is 0 || hasMultiDigitNumber || digits.Any(digit => digit is < '1' or > '4'))
        {
            return false;
        }

        set = new PhaseSet([.. digits.Select(digit => (Phase)(digit - '0'))]);
        return true;
    }

    /// <inheritdoc/>
    public override string ToString()
    {
        string[] names = [.. Phases.Select(Ordinal)];
        return names.Length switch
        {
            0 => "none",
            1 => names[0],
            _ => $"{string.Join(", ", names[..^1])} or {names[^1]}",
        };
    }

    private static byte Bit(Phase phase) => (byte)(1 << ((int)phase - 1));
}
