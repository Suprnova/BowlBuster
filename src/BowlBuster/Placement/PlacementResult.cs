namespace BowlBuster.Placement;

/// <summary>
/// What <see cref="Placer"/> made of a placement: the sphere, or why there is none. The family is closed.
/// </summary>
public abstract record PlacementResult;

/// <summary>
/// The landing placed.
/// </summary>
/// <param name="Sphere">The replayed address of the block plus the offset, wrapped to 32 bits: the stale pointer <c>S</c> to write.</param>
/// <param name="Top">
/// The heap's cursor and depth the replay has at the recipe's cutoff, for the harness to compare with the live heap at
/// the first stale write; <see langword="null"/> when the recipe load has no cutoff.
/// </param>
public sealed record Placed(uint Sphere, HeapTop? Top) : PlacementResult;

/// <summary>
/// No landing: the op names no block of the recipe load, or one the live heap can't hold.
/// </summary>
/// <param name="Reason">Why, for a person.</param>
public sealed record NoBlock(string Reason) : PlacementResult;

/// <summary>
/// No landing: the recipe has no such load, or its requests don't replay from the live heap.
/// </summary>
/// <param name="Reason">Why, for a person.</param>
public sealed record Unplaceable(string Reason) : PlacementResult;

/// <summary>
/// No landing yet: more than one segment holds the load, and the request named none.
/// </summary>
/// <param name="Segments">The segments that hold it.</param>
public sealed record AmbiguousLoad(IReadOnlyList<int> Segments) : PlacementResult;

/// <summary>
/// A heap's cursor and depth.
/// </summary>
/// <param name="Cursor">The current depth's cursor.</param>
/// <param name="Depth">The current depth.</param>
public readonly record struct HeapTop(uint Cursor, int Depth);
