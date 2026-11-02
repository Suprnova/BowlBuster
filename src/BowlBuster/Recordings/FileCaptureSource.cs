using System.Text.Json;

namespace BowlBuster.Recordings;

/// <summary>
/// Finds the captures in a recording's directory.
/// </summary>
/// <remarks>
/// A capture is a directory under <c>captures</c> holding a manifest, the heap's bytes and a completion marker. A
/// capture without its marker was not finished, and is not found.
/// </remarks>
/// <param name="recordingDirectory">The recording's directory.</param>
public sealed class FileCaptureSource(string recordingDirectory) : ICaptureSource
{
    private const string CapturesDirectory = "captures";
    private const string Marker = "complete";

    private readonly string recordingDirectory = recordingDirectory ?? throw new ArgumentNullException(nameof(recordingDirectory));

    /// <inheritdoc/>
    /// <remarks>
    /// Only the recording in this source's directory is found: another <paramref name="recordingId"/> finds nothing.
    /// </remarks>
    /// <exception cref="FormatException">The capture's manifest is not valid.</exception>
    public ILoadCapture? Find(string recordingId, string captureId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(recordingId);
        ArgumentException.ThrowIfNullOrWhiteSpace(captureId);

        if (captureId != Path.GetFileName(captureId) || !string.Equals(recordingId, RunId(), StringComparison.Ordinal)) return null;

        string directory = Path.Combine(recordingDirectory, CapturesDirectory, captureId);
        string manifestPath = Path.Combine(directory, RecordingDirectory.ManifestFile);
        if (!File.Exists(Path.Combine(directory, Marker)) || !File.Exists(manifestPath)) return null;

        try
        {
            using JsonDocument manifest = JsonDocument.Parse(File.ReadAllText(manifestPath));
            JsonElement root = manifest.RootElement;
            JsonElement heap = root.GetProperty("heap");
            uint cursor = heap.GetProperty("states")[heap.GetProperty("depth").GetInt32()].GetProperty("cursor").GetUInt32();
            JsonElement range = root.GetProperty("ranges").GetProperty("heap0");
            string file = Path.Combine(directory, Path.GetFileName(range.GetProperty("file").GetString()!));

            return File.Exists(file) ? new HeapBytes(range.GetProperty("address").GetUInt32(), cursor, File.ReadAllBytes(file)) : null;
        }
        catch (Exception exception) when (exception is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or ArgumentOutOfRangeException)
        {
            throw new FormatException($"The manifest of the capture '{captureId}' at '{directory}' is not valid: {exception.Message}", exception);
        }
    }

    private string? RunId()
    {
        using JsonDocument manifest = JsonDocument.Parse(File.ReadAllText(Path.Combine(recordingDirectory, RecordingDirectory.ManifestFile)));
        return manifest.RootElement.TryGetProperty("run", out JsonElement run) ? run.GetString() : null;
    }

    private sealed class HeapBytes(uint start, uint top, byte[] bytes) : ILoadCapture
    {
        public uint HeapTop { get; } = top;

        public bool TryRead(uint address, Span<byte> destination)
        {
            if (address < start) return false;

            ulong offset = address - start;
            if (offset + (ulong)destination.Length > (ulong)bytes.Length) return false;

            bytes.AsSpan((int)offset, destination.Length).CopyTo(destination);
            return true;
        }
    }
}
