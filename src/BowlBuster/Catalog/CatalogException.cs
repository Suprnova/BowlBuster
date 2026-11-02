using System.Diagnostics.CodeAnalysis;

namespace BowlBuster.Catalog;

/// <summary>
/// A catalog file could not be read: it is not valid YAML, or it breaks the catalog's rules.
/// </summary>
/// <param name="file">The file, or whatever else the catalog was read from.</param>
/// <param name="problems">Every problem found in it.</param>
[SuppressMessage("Design", "CA1032:Implement standard exception constructors", Justification = "An exception without a file and its problems would say nothing.")]
public sealed class CatalogException(string file, IReadOnlyList<string> problems) : Exception(Describe(file, problems))
{
    /// <summary>
    /// The file, or whatever else the catalog was read from.
    /// </summary>
    public string File { get; } = file;

    /// <summary>
    /// Every problem found in the catalog.
    /// </summary>
    public IReadOnlyList<string> Problems { get; } = problems;

    private static string Describe(string file, IReadOnlyList<string> problems)
    {
        ArgumentNullException.ThrowIfNull(problems);
        return $"{file} has {problems.Count} problem(s):{string.Concat(problems.Select(static problem => $"{Environment.NewLine}- {problem}"))}";
    }
}
