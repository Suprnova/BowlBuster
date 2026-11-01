namespace BowlBuster.Replay;

/// <summary>
/// The checks a recording must pass before it is used.
/// </summary>
public enum ReplayCheck
{
    /// <summary>
    /// The recording was made on the platform being replayed.
    /// </summary>
    Platform,

    /// <summary>
    /// The harness lost no events, since a lost event can hide a request or move a cutoff.
    /// </summary>
    DroppedEvents,

    /// <summary>
    /// Every request is one the allocator can run. The game never makes one it can't, so such a recording is corrupt.
    /// </summary>
    IllegalRequest,

    /// <summary>
    /// Every allocation returned the address the game returned.
    /// </summary>
    ReturnedAddress,

    /// <summary>
    /// Every pool allocation returned the instance the game returned.
    /// </summary>
    PoolInstance,

    /// <summary>
    /// The heap after a load's last request is the state the next load started from.
    /// </summary>
    EndState,

    /// <summary>
    /// The cursor at the cutoff is the top of the cutoff's capture.
    /// </summary>
    CutoffCursor,
}
