using BowlBuster.Recordings;

namespace BowlBuster.Tests.Recordings;

/// <summary>
/// A capture filled with a computed pattern, so no test holds a byte of the game.
/// </summary>
internal sealed class FakeCapture(uint heapTop) : ILoadCapture
{
    public uint HeapTop { get; } = heapTop;

    public static byte ByteAt(uint address) => (byte)((address * 0x9E3779B1) >> 24);

    public bool TryRead(uint address, Span<byte> destination)
    {
        if (address + (uint)destination.Length > HeapTop) return false;

        for (int index = 0; index < destination.Length; index++)
        {
            destination[index] = ByteAt(address + (uint)index);
        }

        return true;
    }
}

internal sealed class FakeCaptures(IReadOnlyDictionary<string, uint> tops) : ICaptureSource
{
    public ILoadCapture? Find(string recordingId, string captureId) =>
        tops.TryGetValue(captureId, out uint top) ? new FakeCapture(top) : null;
}
