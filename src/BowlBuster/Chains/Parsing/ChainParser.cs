using BowlBuster.Catalog;
using BowlBuster.Loads;
using System.Buffers;
using System.Globalization;
using System.Text.RegularExpressions;

namespace BowlBuster.Chains.Parsing;

/// <summary>
/// Reads a chain as runners write it: steps joined by " &gt; ", beginning with <c>[load]</c> and <c>burn xN</c> for a
/// full chain, and ending with <c>[target: 4th or 1st]</c> for a shape.
/// </summary>
internal static partial class ChainParser
{
    private const string GenericFiller = "non-SB";

    private static readonly SearchValues<char> UnnameableCharacters = SearchValues.Create(">,()[]");

    public static Chain Parse(string text, Vocabulary vocabulary)
    {
        PhaseSet? targetPhases = null;
        if (TargetPhases().Match(text) is { Success: true } phases)
        {
            targetPhases = PhaseSet.TryParse(phases.Groups["phases"].Value, out PhaseSet set)
                ? set
                : throw new FormatException($"'{phases.Groups["phases"].Value.Trim()}' is not a list of phases such as '4th or 1st'.");
            text = text[..phases.Index];
        }

        string[] steps = text.Split('>', StringSplitOptions.TrimEntries);
        if (steps.Any(string.IsNullOrEmpty)) throw new FormatException("A chain can't have an empty step.");

        int? burns = null;
        int first = 0;
        if (LoadMarker().IsMatch(steps[0]))
        {
            burns = 0;
            first = 1;
            if (steps.Length > 1 && BurnWord().IsMatch(steps[1]))
            {
                Match burn = Burn().Match(steps[1]);
                if (!burn.Success) throw new FormatException($"'{steps[1]}' isn't a burn: write 'burn xN', without naming a level.");

                burns = ReadCount(burn.Groups["count"].Value, steps[1]);
                first = 2;
            }
        }

        string[] levels = steps[first..];
        if (levels.Length < 2) throw new FormatException("A chain needs an origin and a target.");

        foreach (string step in levels)
            if (LoadMarker().IsMatch(step) || BurnWord().IsMatch(step))
                throw new FormatException($"'{step}' can only come directly after the start of a chain that begins at [load].");

        LevelStep origin = ReadLevel(levels[0], "origin", vocabulary);
        FillerStep[] fillers = [.. levels[1..^1].Select(step => ReadFiller(step, vocabulary))];
        LevelStep target = ReadLevel(levels[^1], "target", vocabulary);

        try
        {
            return new Chain(burns, origin, fillers, target, targetPhases);
        }
        catch (ArgumentException exception)
        {
            throw new FormatException(exception.Message, exception);
        }
    }

    public static bool CanName(string name) =>
        name.AsSpan().IndexOfAny(UnnameableCharacters) < 0
        && !BurnWord().IsMatch(name)
        && !TrailingCount().IsMatch(name)
        && !name.Trim().Equals(GenericFiller, StringComparison.OrdinalIgnoreCase);

    private static LevelStep ReadLevel(string step, string role, Vocabulary vocabulary)
    {
        Match match = Step().Match(step);
        if (!match.Success) throw new FormatException($"The {role} '{step}' isn't a level with optional costumes.");

        string name = match.Groups["name"].Value;
        if (name.Equals(GenericFiller, StringComparison.OrdinalIgnoreCase)) throw new FormatException($"The {role} must be a named level, not {GenericFiller}.");
        if (match.Groups["count"].Success) throw new FormatException($"The {role} '{step}' is one load, so it takes no count.");

        Costumes costumes = match.Groups["costumes"].Success ? ReadCostumes(match.Groups["costumes"].Value, step, vocabulary) : Costumes.None;
        return new LevelStep(vocabulary.ResolveLevel(name), costumes);
    }

    private static FillerStep ReadFiller(string step, Vocabulary vocabulary)
    {
        Match match = Step().Match(step);
        if (!match.Success) throw new FormatException($"The filler '{step}' isn't a level or {GenericFiller} with an optional count.");
        if (match.Groups["costumes"].Success) throw new FormatException($"The filler '{step}' can't have costumes: only the origin and the target do.");

        string name = match.Groups["name"].Value;
        int count = match.Groups["count"].Success ? ReadCount(match.Groups["count"].Value, step) : 1;
        return new FillerStep(name.Equals(GenericFiller, StringComparison.OrdinalIgnoreCase) ? null : vocabulary.ResolveLevel(name), count);
    }

    private static Costumes ReadCostumes(string text, string step, Vocabulary vocabulary)
    {
        string[] written = text.Split(',', StringSplitOptions.TrimEntries);
        if (written.Length > 2 || written.Any(string.IsNullOrEmpty))
            throw new FormatException($"'{step}' needs one or two costumes, SpongeBob's first.");

        return vocabulary.ResolveCostumes(written);
    }

    private static int ReadCount(string digits, string step) =>
        int.TryParse(digits, NumberStyles.None, CultureInfo.InvariantCulture, out int count) && count >= 1
            ? count
            : throw new FormatException($"'{step}' needs a count of 1 or more.");

    [GeneratedRegex(@"\[\s*target\s*:(?<phases>[^\]]*)\]\s*$", RegexOptions.IgnoreCase)]
    private static partial Regex TargetPhases();

    [GeneratedRegex(@"\sx\d+\s*$", RegexOptions.IgnoreCase)]
    private static partial Regex TrailingCount();

    [GeneratedRegex(@"^\[\s*load\s*\]$", RegexOptions.IgnoreCase)]
    private static partial Regex LoadMarker();

    [GeneratedRegex(@"^burn(\s|$)", RegexOptions.IgnoreCase)]
    private static partial Regex BurnWord();

    [GeneratedRegex(@"^burn\s+x(?<count>\d+)$", RegexOptions.IgnoreCase)]
    private static partial Regex Burn();

    [GeneratedRegex(@"^(?<name>[^()\[\]]+?)\s*(?:\((?<costumes>[^)]*)\))?(?:\s+x(?<count>\d+))?$", RegexOptions.IgnoreCase)]
    private static partial Regex Step();
}
