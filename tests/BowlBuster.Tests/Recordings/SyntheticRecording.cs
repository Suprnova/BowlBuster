namespace BowlBuster.Tests.Recordings;

/// <summary>
/// The synthetic recording the harness's tests wrote and committed, and a copy of it a test may damage.
/// </summary>
internal sealed class SyntheticRecording : IDisposable
{
    public const string RunId = "run-1";

    private readonly DirectoryInfo? copy;

    private SyntheticRecording(string path, DirectoryInfo? copy)
    {
        Path = path;
        this.copy = copy;
    }

    public string Path { get; }

    public static string Committed { get; } = System.IO.Path.Combine(AppContext.BaseDirectory, "Recordings", "Fixtures", "synthetic");

    public static SyntheticRecording CopyOfCommitted()
    {
        DirectoryInfo directory = Directory.CreateTempSubdirectory("bowlbuster-recording-");
        CopyInto(new DirectoryInfo(Committed), directory);
        return new SyntheticRecording(directory.FullName, directory);
    }

    public string FileOf(params string[] relative) => System.IO.Path.Combine([Path, .. relative]);

    public void Dispose() => copy?.Delete(recursive: true);

    private static void CopyInto(DirectoryInfo source, DirectoryInfo target)
    {
        foreach (FileInfo file in source.GetFiles())
            file.CopyTo(System.IO.Path.Combine(target.FullName, file.Name));

        foreach (DirectoryInfo directory in source.GetDirectories())
            CopyInto(directory, target.CreateSubdirectory(directory.Name));
    }
}
