using BowlBuster.Memory;
using BowlBuster.Placement;
using BowlBuster.Platforms;
using BowlBuster.Recordings;
using BowlBuster.Replay;
using System.CommandLine;

namespace BowlBuster.Cli;

/// <summary>
/// <c>bowlbuster place</c>: where a landing test's stale pointer goes, for the harness to write.
/// </summary>
/// <remarks>
/// Prints <c>0x&lt;S&gt;</c> on stdout and, with <c>--top</c>, <c>0x&lt;cursor&gt; &lt;depth&gt;</c> on a second line,
/// and nothing on stdout unless it exits 0. The reason for any other exit is on stderr: 64 for a malformed call or heap
/// file, or a load more than one segment holds when no segment was named; 65 when the op names no block; 66 when the
/// recording can't be read, fails replay validation, or has no such load, or its requests don't replay from the heap.
/// </remarks>
internal static class PlaceCommand
{
    public static Command Build(TextWriter output, TextWriter error)
    {
        Option<DirectoryInfo> recording = new("--recording") { Description = "The recipe recording's directory.", Required = true };
        Option<int> load = new("--load") { Description = "The recipe load's counter.", Required = true };
        Option<int?> segment = new("--segment") { Description = "The segment that holds the load, when more than one does." };
        Option<FileInfo> heap = new("--heap") { Description = "The live heap state, spelled as a scene_init event's heap.", Required = true };
        Option<int> op = new("--op") { Description = "The block's position in the load's request list.", Required = true };
        Option<int> delta = new("--delta") { Description = "The signed byte offset of the pointer in the block.", Required = true };
        Option<bool> top = new("--top") { Description = "Also print the cursor and depth the replay has at the cutoff." };

        Command command = new("place", "Place a landing test's stale pointer.") { recording, load, segment, heap, op, delta, top };
        command.SetAction(parsed => Run(
            parsed.GetRequiredValue(recording),
            parsed.GetValue(load),
            parsed.GetValue(segment),
            parsed.GetRequiredValue(heap),
            parsed.GetValue(op),
            parsed.GetValue(delta),
            parsed.GetValue(top),
            output,
            error));
        return command;
    }

    private static int Run(DirectoryInfo directory, int load, int? segment, FileInfo heapFile, int op, int delta, bool withTop, TextWriter output, TextWriter error)
    {
        HeapSnapshot live;
        try
        {
            using StreamReader heap = heapFile.OpenText();
            live = RecordingReader.ReadHeap(heap);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or FormatException)
        {
            error.WriteLine($"Cannot read the heap state: {exception.Message}");
            return CommandLineApp.Usage;
        }

        Recording recipe;
        try
        {
            recipe = RecordingDirectory.Read(directory.FullName, Catalog.Vocabulary.Empty);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or FormatException)
        {
            error.WriteLine($"Cannot read the recording: {exception.Message}");
            return CommandLineApp.Unreadable;
        }

        RecordingValidation validation = new ReplayValidator(PlatformProfile.XboxNtscU, new FileCaptureSource(directory.FullName)).Validate(recipe);
        if (!validation.IsAccepted)
        {
            error.WriteLine($"Rejected {recipe.Id}: {validation.Rejection}");
            return CommandLineApp.Unreadable;
        }

        switch (new Placer(PlatformProfile.XboxNtscU).Place(validation.Recording, load, segment, live, op, delta))
        {
            case Placed placed:
                output.WriteLine($"0x{placed.Sphere:x8}");
                if (withTop && placed.Top is { } heapTop) output.WriteLine($"0x{heapTop.Cursor:x8} {heapTop.Depth}");
                return CommandLineApp.Success;

            case NoBlock none:
                error.WriteLine(none.Reason);
                return CommandLineApp.Rejected;

            case AmbiguousLoad ambiguous:
                error.WriteLine($"Segments {string.Join(", ", ambiguous.Segments)} each hold load {load}: name one with --segment.");
                return CommandLineApp.Usage;

            case Unplaceable unplaceable:
                error.WriteLine(unplaceable.Reason);
                return CommandLineApp.Unreadable;

            default:
                throw new InvalidOperationException("An unknown placement.");
        }
    }
}
