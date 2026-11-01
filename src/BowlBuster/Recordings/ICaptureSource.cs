namespace BowlBuster.Recordings;

/// <summary>
/// Finds the captures a recording kept.
/// </summary>
public interface ICaptureSource
{
    /// <summary>
    /// Finds a capture.
    /// </summary>
    /// <param name="recordingId">The recording's <see cref="Recording.Id"/>.</param>
    /// <param name="captureId">The capture's <see cref="Cutoff.CaptureId"/>.</param>
    /// <returns>The capture, or <see langword="null"/> when it wasn't kept.</returns>
    ILoadCapture? Find(string recordingId, string captureId);
}

/// <summary>
/// Heap 0 as the game held it at a load's cutoff.
/// </summary>
public interface ILoadCapture
{
    /// <summary>
    /// The first address past the captured heap, which is the cursor when the capture was taken.
    /// </summary>
    uint HeapTop { get; }

    /// <summary>
    /// Reads bytes from the captured heap.
    /// </summary>
    /// <param name="address">The address of the first byte, as the recording's run saw it.</param>
    /// <param name="destination">Receives the bytes.</param>
    /// <returns><see langword="true"/> when the capture holds every byte asked for.</returns>
    bool TryRead(uint address, Span<byte> destination);
}
