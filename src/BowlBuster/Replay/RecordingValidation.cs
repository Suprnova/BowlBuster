using BowlBuster.Recordings;
using System.Diagnostics.CodeAnalysis;

namespace BowlBuster.Replay;

/// <summary>
/// What replay validation decided about a recording.
/// </summary>
/// <param name="Recording">The recording, when it was accepted.</param>
/// <param name="Rejection">The first mismatch, when it was rejected.</param>
public sealed record RecordingValidation(ValidatedRecording? Recording, ReplayMismatch? Rejection)
{
    /// <summary>
    /// Whether the recording passed every check.
    /// </summary>
    [MemberNotNullWhen(true, nameof(Recording))]
    [MemberNotNullWhen(false, nameof(Rejection))]
    public bool IsAccepted => Recording is not null;
}

/// <summary>
/// A recording that replay validation accepted. Only <see cref="ReplayValidator"/> makes one, so whatever takes this type
/// can't be handed a recording that failed.
/// </summary>
public sealed class ValidatedRecording
{
    internal ValidatedRecording(Recording recording) => Recording = recording;

    /// <summary>
    /// The recording.
    /// </summary>
    public Recording Recording { get; }
}
