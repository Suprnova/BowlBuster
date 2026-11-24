using BowlBuster.Platforms;
using BowlBuster.Recordings;
using System.Buffers.Binary;

namespace BowlBuster.Discs;

/// <summary>
/// How a captured layer block compares with its layer's image on disc.
/// </summary>
public enum LayerMatch
{
    /// <summary>The capture holds the image byte for byte.</summary>
    Same,

    /// <summary>The capture differs from the image in the listed words: load-time fixups, or a mapping fault.</summary>
    Differs,

    /// <summary>The disc has no layer of that archive, index and size.</summary>
    NotOnDisc,

    /// <summary>No capture holds the block: the load has none, or the block came after it.</summary>
    NotCaptured,
}

/// <summary>
/// One word where a capture differs from the layer's image on disc.
/// </summary>
/// <param name="Offset">The word's offset in the block, a multiple of 4.</param>
/// <param name="Captured">The word the capture holds, little-endian.</param>
/// <param name="OnDisc">The word the image holds, little-endian; bytes past the image's end read as zero.</param>
/// <param name="Asset">The name of the asset that holds the word, or <see langword="null"/> in the padding between two.</param>
/// <param name="OffsetInAsset">The word's offset in that asset, or in the padding.</param>
public readonly record struct LayerDifference(uint Offset, uint Captured, uint OnDisc, string? Asset, uint OffsetInAsset);

/// <summary>
/// A class-1 layer block of a recording, compared with its layer's image on disc.
/// </summary>
/// <param name="Segment">The segment of the load that allocated the block.</param>
/// <param name="Load">The load.</param>
/// <param name="Op">The allocation's position in the load.</param>
/// <param name="Layer">The archive and layer the loader was loading.</param>
/// <param name="Address">The block's address in the recording's run.</param>
/// <param name="Size">The block's size.</param>
/// <param name="Match">How the capture compares with the image.</param>
/// <param name="Differences">The differing words, when <paramref name="Match"/> is <see cref="LayerMatch.Differs"/>.</param>
public sealed record LayerComparison(
    int Segment,
    RecordedLoad Load,
    int Op,
    LayerId Layer,
    uint Address,
    uint Size,
    LayerMatch Match,
    IReadOnlyList<LayerDifference> Differences);

/// <summary>
/// Checks that a recording's class-1 layer blocks hold their layers' images as the disc has them, which is how the
/// simulator maps a layer into its block (4.3).
/// </summary>
/// <param name="profile">The platform's constants.</param>
/// <param name="disc">The disc's layers.</param>
/// <param name="captures">The recording's captures.</param>
public sealed class LayerCheck(PlatformProfile profile, DiscLayers disc, ICaptureSource captures)
{
    /// <summary>
    /// Compares every class-1 layer block of <paramref name="recording"/> with the disc, in recording order.
    /// </summary>
    /// <param name="recording">A recording replay validation accepted.</param>
    /// <returns>One comparison per block.</returns>
    public IReadOnlyList<LayerComparison> Compare(Recording recording)
    {
        ArgumentNullException.ThrowIfNull(recording);
        return
        [
            .. from segment in recording.Segments
               from load in segment.Loads
               from block in LayerBlocks(load)
               select Compare(recording, segment, load, block.Op, block.Request)
        ];
    }

    private IEnumerable<(int Op, AllocRequest Request)> LayerBlocks(RecordedLoad load) =>
        load.Heap.Requests
            .Select(static (request, op) => (Op: op, Request: request as AllocRequest))
            .Where(block => block.Request is { Layer: not null } request && request.Caller == profile.Sites.ArchiveLayer)
            .Select(static block => (block.Op, block.Request!));

    private LayerComparison Compare(Recording recording, RecordingSegment segment, RecordedLoad load, int op, AllocRequest request)
    {
        LayerId layer = request.Layer!.Value;
        LayerComparison Result(LayerMatch match, IReadOnlyList<LayerDifference>? differences = null) =>
            new(segment.Index, load, op, layer, request.Address, request.Size, match, differences ?? []);

        if (disc.Match(layer, request.Size) is not { } onDisc) return Result(LayerMatch.NotOnDisc);

        byte[] captured = new byte[onDisc.Image.Length];
        bool held = load.Heap.Cutoff is { CaptureId: { } captureId } cutoff
            && op < cutoff.RequestCount
            && captures.Find(recording.Id, captureId)?.TryRead(request.Address, captured) is true;
        if (!held) return Result(LayerMatch.NotCaptured);

        ReadOnlySpan<byte> image = onDisc.Image.Span;
        List<LayerDifference> differences = [];
        for (int offset = 0; offset < image.Length; offset += sizeof(uint))
        {
            int length = Math.Min(sizeof(uint), image.Length - offset);
            if (captured.AsSpan(offset, length).SequenceEqual(image.Slice(offset, length))) continue;

            var location = onDisc.Layout.Locate((uint)offset)!.Value;
            differences.Add(new LayerDifference(
                (uint)offset,
                WordAt(captured, offset, length),
                WordAt(image, offset, length),
                location.Asset?.Name,
                location.OffsetInEntry));
        }

        return Result(differences.Count == 0 ? LayerMatch.Same : LayerMatch.Differs, differences);
    }

    private static uint WordAt(ReadOnlySpan<byte> bytes, int offset, int length)
    {
        Span<byte> word = stackalloc byte[sizeof(uint)];
        bytes.Slice(offset, length).CopyTo(word);
        return BinaryPrimitives.ReadUInt32LittleEndian(word);
    }
}
