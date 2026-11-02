using BowlBuster.Catalog;
using System.CommandLine;
using System.CommandLine.Invocation;
using System.CommandLine.Parsing;
using System.Reflection;

namespace BowlBuster.Cli;

/// <summary>
/// The command-line application: builds the commands and runs them.
/// </summary>
internal static class CommandLineApp
{
    /// <summary>
    /// The exit code for an accepted recording, and for any command that succeeded.
    /// </summary>
    public const int Success = 0;

    /// <summary>
    /// The exit code for a call that isn't a valid use of a command.
    /// </summary>
    public const int Usage = 64;

    /// <summary>
    /// The exit code for a recording that replay validation rejected.
    /// </summary>
    public const int Rejected = 65;

    /// <summary>
    /// The exit code for a recording that could not be read.
    /// </summary>
    public const int Unreadable = 66;

    /// <summary>
    /// The exit code for a failure in BowlBuster itself.
    /// </summary>
    public const int Internal = 70;

    /// <summary>
    /// Runs the application.
    /// </summary>
    /// <param name="args">The command line.</param>
    /// <param name="output">Where results go.</param>
    /// <param name="error">Where problems go.</param>
    /// <returns>The exit code.</returns>
    public static int Run(string[] args, TextWriter output, TextWriter error)
    {
        RootCommand root = Build(output, error);
        ParseResult parsed = root.Parse(args);

        if (parsed.Errors.Count > 0)
        {
            foreach (ParseError problem in parsed.Errors) error.WriteLine(problem.Message);
            error.WriteLine("Try --help.");
            return Usage;
        }

        try
        {
            return parsed.Invoke(new InvocationConfiguration { Output = output, Error = error });
        }
        catch (Exception exception) when (exception is not OutOfMemoryException)
        {
            error.WriteLine($"BowlBuster failed: {exception.Message}");
            return Internal;
        }
    }

    private static RootCommand Build(TextWriter output, TextWriter error)
    {
        RootCommand root = new("BowlBuster studies Bowl Storage in The SpongeBob SquarePants Movie.");
        if (root.Options.FirstOrDefault(static option => option.Name == "--version") is { } version)
            version.Action = new BannerAction(output);

        Command recordings = new("recordings", "Work with the harness's recordings.");
        recordings.Subcommands.Add(ValidateCommand.Build(output, error, LoadVocabulary));
        root.Subcommands.Add(recordings);

        return root;
    }

    private static Vocabulary LoadVocabulary(DirectoryInfo? catalog) => catalog is null ? Vocabulary.Empty : Vocabulary.Load(catalog.FullName);

    private sealed class BannerAction(TextWriter output) : SynchronousCommandLineAction
    {
        public override int Invoke(ParseResult parseResult)
        {
            output.WriteLine(VersionBanner.For(Assembly.GetExecutingAssembly()));
            return Success;
        }
    }
}
