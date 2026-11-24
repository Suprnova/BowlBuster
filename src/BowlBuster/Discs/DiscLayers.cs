using BowlBuster.Landings;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using EvilHop;
using EvilHop.Assets;
using EvilHop.Common;

namespace BowlBuster.Discs;

/// <summary>
/// The archive layers of an extracted disc, as the game maps them into heap blocks.
/// </summary>
/// <remarks>
/// A layer is named as a recording names it: the archive's file name relative to the disc's root, with <c>\</c> between
/// folders and without the <c>.HIP</c> extension (a <c>.HOP</c> keeps its own), and the layer's index in the archive. The
/// names resolve ignoring case, since the disc mixes it. An archive that doesn't resolve is absent, not an error.
/// <para>
/// A block is a layer's only when its size is the layer image's length rounded up to
/// <see cref="PlatformProfile.LayerRounding"/>. An asset directory comes from the same allocator, so a block that doesn't
/// match has no answer.
/// </para>
/// </remarks>
/// <param name="root">The extracted disc's root directory.</param>
/// <param name="profile">The platform whose build the disc holds.</param>
public sealed class DiscLayers(string root, PlatformProfile profile) : ILayerImageSource
{
    private const string HipExtension = ".HIP";

    private readonly Platform platform = profile.Platform switch
    {
        "xbox" => Platform.Xbox,
        _ => throw new ArgumentException($"There is no EvilHop platform for '{profile.Platform}'.", nameof(profile)),
    };

    private readonly Dictionary<string, AssetView?> views = new(StringComparer.OrdinalIgnoreCase);

    /// <inheritdoc/>
    public bool TryRead(LayerId layer, uint blockSize, uint offset, Span<byte> destination)
    {
        if (ImageOf(layer, blockSize) is not { } image || offset + (uint)destination.Length > (uint)image.Length) return false;

        image.Span.Slice((int)offset, destination.Length).CopyTo(destination);
        return true;
    }

    private ReadOnlyMemory<byte>? ImageOf(LayerId layer, uint blockSize)
    {
        if (ViewOf(layer.Archive) is not { } view || layer.Layer < 0 || layer.Layer >= view.Layers.Count) return null;

        var image = view.GetLayerImage(layer.Layer);
        return RoundUp((uint)image.Length, profile.LayerRounding) == blockSize ? image : null;
    }

    private AssetView? ViewOf(string archive)
    {
        if (views.TryGetValue(archive, out var known)) return known;

        AssetView? view = null;
        if (Resolve(archive) is { } path)
        {
            using var stream = File.OpenRead(path);
            view = Archive.Load(stream, GameVersion.TSSM, platform).ReadAssets();
        }
        return views[archive] = view;
    }

    private string? Resolve(string archive)
    {
        string[] segments = archive.Split('\\');
        if (!Path.HasExtension(segments[^1])) segments[^1] += HipExtension;

        string? path = root;
        foreach (string segment in segments)
            path = path is not null && Directory.Exists(path) ? EntryNamed(path, segment) : null;
        return path is not null && File.Exists(path) ? path : null;
    }

    private static string? EntryNamed(string directory, string name) =>
        Directory.EnumerateFileSystemEntries(directory)
            .FirstOrDefault(entry => string.Equals(Path.GetFileName(entry), name, StringComparison.OrdinalIgnoreCase));

    private static uint RoundUp(uint length, uint multiple) => (length + multiple - 1) / multiple * multiple;
}
