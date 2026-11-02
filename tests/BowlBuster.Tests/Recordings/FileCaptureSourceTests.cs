using BowlBuster.Recordings;

namespace BowlBuster.Tests.Recordings;

public class FileCaptureSourceTests
{
    private const string Cutoff = "0-2-cutoff";

    private const uint HeapBase = 0x5C0030;

    private const uint HeapTop = 0x5C0130;

    private readonly FileCaptureSource source = new(SyntheticRecording.Committed);

    [Fact]
    public void Find_CompleteCapture_TakesTheHeapTopFromTheCursor()
    {
        ILoadCapture? capture = source.Find(SyntheticRecording.RunId, Cutoff);

        Assert.NotNull(capture);
        Assert.Equal(HeapTop, capture.HeapTop);
    }

    [Theory]
    [InlineData(0u, 4)]
    [InlineData(5u, 3)]
    [InlineData(250u, 6)]
    public void TryRead_InsideTheCapturedHeap_ReturnsTheCapturedBytes(uint offset, int length)
    {
        ILoadCapture capture = source.Find(SyntheticRecording.RunId, Cutoff)!;
        byte[] bytes = new byte[length];

        bool read = capture.TryRead(HeapBase + offset, bytes);

        Assert.True(read);
        Assert.Equal(Enumerable.Range((int)offset, length).Select(static index => (byte)(index % 241)), bytes);
    }

    [Theory]
    [InlineData(HeapBase - 1, 4)]
    [InlineData(HeapBase + 253, 4)]
    [InlineData(HeapTop, 1)]
    public void TryRead_OutsideTheCapturedHeap_ReturnsFalse(uint address, int length)
    {
        ILoadCapture capture = source.Find(SyntheticRecording.RunId, Cutoff)!;

        bool read = capture.TryRead(address, new byte[length]);

        Assert.False(read);
    }

    [Fact]
    public void Find_CaptureWithoutItsMarker_ReturnsNull()
    {
        using SyntheticRecording recording = SyntheticRecording.CopyOfCommitted();
        File.Delete(recording.FileOf("captures", Cutoff, "complete"));

        ILoadCapture? capture = new FileCaptureSource(recording.Path).Find(SyntheticRecording.RunId, Cutoff);

        Assert.Null(capture);
    }

    [Theory]
    [InlineData("0-9-cutoff")]
    [InlineData("..")]
    [InlineData("../captures/0-2-cutoff")]
    public void Find_CaptureThatWasNotKept_ReturnsNull(string captureId) =>
        Assert.Null(source.Find(SyntheticRecording.RunId, captureId));

    [Fact]
    public void Find_OtherRecordingsCapture_ReturnsNull() =>
        Assert.Null(source.Find("another-run", Cutoff));

    [Fact]
    public void Find_CaptureWithABrokenManifest_ThrowsNamingTheCapture()
    {
        using SyntheticRecording recording = SyntheticRecording.CopyOfCommitted();
        File.WriteAllText(recording.FileOf("captures", Cutoff, "manifest.json"), "{}");

        FormatException exception = Assert.Throws<FormatException>(() => new FileCaptureSource(recording.Path).Find(SyntheticRecording.RunId, Cutoff));

        Assert.Contains(Cutoff, exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Find_CaptureWhoseBytesAreMissing_ReturnsNull()
    {
        using SyntheticRecording recording = SyntheticRecording.CopyOfCommitted();
        File.Delete(recording.FileOf("captures", Cutoff, "heap0.bin"));

        Assert.Null(new FileCaptureSource(recording.Path).Find(SyntheticRecording.RunId, Cutoff));
    }
}
