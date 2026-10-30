namespace BowlBuster.Loads;

/// <summary>
/// Where a load falls in the heap layout's period of four, named as runners name it. The 1st, 2nd, 3rd and 4th load are
/// the loads whose number modulo 4 is 1, 2, 3 and 0.
/// </summary>
public enum Phase
{
    /// <summary>
    /// Load numbers 1, 5, 9 and so on.
    /// </summary>
    First = 1,

    /// <summary>
    /// Load numbers 2, 6, 10 and so on.
    /// </summary>
    Second = 2,

    /// <summary>
    /// Load numbers 3, 7, 11 and so on.
    /// </summary>
    Third = 3,

    /// <summary>
    /// Load numbers 4, 8, 12 and so on.
    /// </summary>
    Fourth = 4,
}
