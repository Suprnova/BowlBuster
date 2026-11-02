namespace BowlBuster.Catalog;

/// <summary>
/// A world of the pause menu: its community name, the text the game shows for it and its task slots.
/// </summary>
/// <param name="Number">The world's number, from 1.</param>
/// <param name="Name">The community name, or <see langword="null"/> when the world has none.</param>
/// <param name="GameName">The in-game text, kept as the game spells it, or <see langword="null"/> when the game has none.</param>
/// <param name="Tasks">The world's task slots, in slot order.</param>
public sealed record WorldName(int Number, string? Name, string? GameName, IReadOnlyList<TaskName> Tasks)
{
    /// <summary>
    /// What BowlBuster prints for the world: <see cref="Name"/>, or else <see cref="GameName"/>.
    /// </summary>
    public string? Label => Name ?? GameName;
}

/// <summary>
/// A task slot of a world: its community name and the text the game shows for it. Display text only: the pause menu's
/// rows decide which scene a slot loads.
/// </summary>
/// <param name="World">The number of the world the slot belongs to.</param>
/// <param name="Slot">The slot's number within its world, from 1.</param>
/// <param name="Name">The community name, or <see langword="null"/> when the slot has none.</param>
/// <param name="GameName">The in-game text, kept as the game spells it, or <see langword="null"/> when the game has none.</param>
public sealed record TaskName(int World, int Slot, string? Name, string? GameName)
{
    /// <summary>
    /// What BowlBuster prints for the slot: <see cref="Name"/>, or else <see cref="GameName"/>.
    /// </summary>
    public string? Label => Name ?? GameName;
}
