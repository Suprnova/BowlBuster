using BowlBuster.Catalog;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Replay;
using System.CommandLine;

namespace BowlBuster.Cli;

/// <summary>
/// What the <c>recordings</c> commands share: the extracted disc, and reading and validating a recording.
/// </summary>
internal static class RecordingInputs
{
    /// <summary>The environment variable naming the extracted disc when <c>--disc</c> doesn't.</summary>
    public const string DiscVariable = "BOWL_DISC";

    /// <summary>
    /// The <c>--disc</c> option.
    /// </summary>
    /// <param name="purpose">What the command reads the disc for, completing "The extracted disc, ...".</param>
    public static Option<DirectoryInfo?> DiscOption(string purpose) =>
        new("--disc") { Description = $"The extracted disc, {purpose}; else {DiscVariable}." };

    /// <summary>
    /// The disc <c>--disc</c> named, else the one <see cref="DiscVariable"/> names, else none.
    /// </summary>
    public static DirectoryInfo? Disc(DirectoryInfo? named) =>
        named ?? (Environment.GetEnvironmentVariable(DiscVariable) is { Length: > 0 } path ? new DirectoryInfo(path) : null);

    /// <summary>
    /// Reads a recording and replays it.
    /// </summary>
    /// <param name="directory">The recording's directory.</param>
    /// <param name="disc">The disc the command will read, checked to be a directory.</param>
    /// <param name="vocabulary">Loads the names to read the recording with.</param>
    /// <param name="error">Where problems go.</param>
    /// <returns>The replayed recording, or <see langword="null"/> after saying why on <paramref name="error"/> when it or the disc can't be read.</returns>
    public static ReplayedRecording? Read(DirectoryInfo directory, DirectoryInfo? disc, Func<Vocabulary> vocabulary, TextWriter error)
    {
        if (disc is { Exists: false })
        {
            error.WriteLine($"Cannot read the disc: {disc.FullName} isn't a directory.");
            return null;
        }

        Recording recording;
        try
        {
            recording = RecordingDirectory.Read(directory.FullName, vocabulary());
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or FormatException or CatalogException)
        {
            error.WriteLine($"Cannot read the recording: {exception.Message}");
            return null;
        }

        FileCaptureSource captures = new(directory.FullName);
        return new ReplayedRecording(recording, captures, new ReplayValidator(PlatformProfile.XboxNtscU, captures).Validate(recording));
    }
}

/// <summary>
/// A recording read and replayed.
/// </summary>
/// <param name="Recording">The recording.</param>
/// <param name="Captures">Its captures.</param>
/// <param name="Result">What replay validation said.</param>
internal sealed record ReplayedRecording(Recording Recording, FileCaptureSource Captures, RecordingValidation Result)
{
    /// <summary>The exit code for the replay's result.</summary>
    public int ExitCode => Result.IsAccepted ? CommandLineApp.Success : CommandLineApp.Rejected;
}
