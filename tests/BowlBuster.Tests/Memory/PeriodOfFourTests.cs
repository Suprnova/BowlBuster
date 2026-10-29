using BowlBuster.Memory;
using BowlBuster.Platforms;

namespace BowlBuster.Tests.Memory;

public class PeriodOfFourTests
{
    private const uint FirstLeakCursor = 0x6E6980;
    private const uint LeakCost = 720;
    private const int Loads = 40;

    private static readonly PlatformProfile Platform = PlatformProfile.XboxNtscU;

    private static readonly Scene[] Scenes =
    [
        new(
            [Alloc(100, 16), Alloc(1, 0), Alloc(32, 16)],
            5000,
            [Alloc(300, 64), Grow(76), Alloc(40, 32), Alloc(7, 16), Grow(12), Alloc(2048, 64), Alloc(9, 0)]),
        new(
            [],
            4096,
            [Alloc(1000, 32), Grow(4), Alloc(64, 64)]),
        new(
            [Alloc(4096, 16), Alloc(12, 4), Alloc(12, 8), Alloc(200, 16), Grow(100)],
            128,
            [Alloc(16, 16), Alloc(17, 32), Grow(3), Alloc(64, 64), Alloc(1, 64)]),
    ];

    private sealed record Step(bool IsGrow, uint Size, uint Alignment);

    private sealed record Scene(Step[] Prefix, uint AnchorSize, Step[] Rest);

    private sealed record LoadResult(uint Anchor, uint[] RestOffsets);

    private static Step Alloc(uint size, uint alignment) => new(false, size, alignment);

    private static Step Grow(uint size) => new(true, size, 0);

    private static GameHeap CreateHeap(uint cursor = FirstLeakCursor) =>
        new(Platform.Heap0, [new HeapState(cursor, 0, 0)]);

    private static uint Apply(GameHeap heap, Step step) =>
        step.IsGrow ? heap.Grow(step.Size) : heap.Allocate(step.Size, step.Alignment);

    private static void Leak(GameHeap heap) => heap.Allocate(Platform.PlayerEntitySize, 0);

    private static LoadResult RunLoad(GameHeap heap, Scene scene)
    {
        Leak(heap);
        heap.Push();
        foreach (Step step in scene.Prefix)
        {
            Apply(heap, step);
        }

        uint anchor = heap.Allocate(scene.AnchorSize, 64);
        uint[] offsets = [.. scene.Rest.Select(step => Apply(heap, step) - anchor)];
        heap.Pop(0);
        return new LoadResult(anchor, offsets);
    }

    private static LoadResult[] RunLoads(Scene scene, int count, GameHeap? heap = null)
    {
        heap ??= CreateHeap();
        return [.. Enumerable.Range(0, count).Select(_ => RunLoad(heap, scene))];
    }

    private static uint[] Anchors(Scene scene, int count) => [.. RunLoads(scene, count).Select(load => load.Anchor)];

    private static uint AlignUp(uint value, uint alignment) => (value + alignment - 1) & ~(alignment - 1);

    private static uint CursorAfterLoads(int loads)
    {
        uint padding = 12 + ((16 - ((FirstLeakCursor + 12) & 15)) & 15);
        return FirstLeakCursor + padding + Platform.PlayerEntitySize + (LeakCost * (uint)(loads - 1));
    }

    private static uint PrefixAdvance(Scene scene)
    {
        GameHeap scratch = CreateHeap(8);
        foreach (Step step in scene.Prefix)
        {
            Apply(scratch, step);
        }

        return scratch.Current.Cursor - 8;
    }

    [Fact]
    public void PrefixAdvance_FirstScene_MatchesTheHandComputedAdvance() =>
        Assert.Equal(184u, PrefixAdvance(Scenes[0]));

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public void Anchor_ConsecutiveLoads_MovesBy704ThreeTimesInFourAnd768Once(int scene)
    {
        uint[] anchors = Anchors(Scenes[scene], Loads);

        uint[] moves = [.. anchors.Zip(anchors.Skip(1), (previous, next) => next - previous)];

        Assert.All(moves, move => Assert.Contains(move, new uint[] { 704, 768 }));
        for (int first = 0; first + 4 <= moves.Length; first++)
        {
            Assert.Equal(2880u, (uint)moves.Skip(first).Take(4).Sum(move => (int)move));
            Assert.Equal(1, moves.Skip(first).Take(4).Count(move => move is 768));
        }
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public void Anchor_ConsecutiveLoads_RepeatsItsMovesEveryFourLoads(int scene)
    {
        uint[] anchors = Anchors(Scenes[scene], Loads);
        uint[] moves = [.. anchors.Zip(anchors.Skip(1), (previous, next) => next - previous)];

        uint[] repeated = [.. moves.Skip(4)];

        Assert.Equal(moves.Take(repeated.Length), repeated);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public void Anchor_AfterEachLoad_MatchesTheLeakArithmetic(int scene)
    {
        uint advance = PrefixAdvance(Scenes[scene]);

        uint[] anchors = Anchors(Scenes[scene], Loads);

        for (int load = 1; load <= Loads; load++)
        {
            Assert.Equal(AlignUp(CursorAfterLoads(load) + advance + 12, 64), anchors[load - 1]);
        }
    }

    [Fact]
    public void Cursor_AfterEachLoad_IsTheFirstLeakPlus720PerLaterLoadAndEightModSixteen()
    {
        GameHeap heap = CreateHeap();

        for (int load = 1; load <= Loads; load++)
        {
            RunLoad(heap, Scenes[0]);

            Assert.Equal(CursorAfterLoads(load), heap.Current.Cursor);
            Assert.Equal(8u, heap.Current.Cursor % 16);
        }
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public void RestOffsets_EveryLoad_AreIdenticalToTheFirstLoads(int scene)
    {
        LoadResult[] loads = RunLoads(Scenes[scene], Loads);

        uint[][] offsets = [.. loads.Select(load => load.RestOffsets)];

        Assert.All(offsets, load => Assert.Equal(offsets[0], load));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(3)]
    [InlineData(7)]
    [InlineData(12)]
    public void Anchor_AfterExtraLeaks_EqualsTheAnchorAfterThatManyLoads(int shift)
    {
        GameHeap shifted = CreateHeap();
        for (int leak = 0; leak < shift; leak++)
        {
            Leak(shifted);
        }

        GameHeap played = CreateHeap();
        RunLoads(Scenes[0], shift, played);

        uint anchorShifted = RunLoad(shifted, Scenes[0]).Anchor;
        uint anchorPlayed = RunLoad(played, Scenes[0]).Anchor;

        Assert.Equal(anchorPlayed, anchorShifted);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(5)]
    [InlineData(6)]
    [InlineData(7)]
    [InlineData(9)]
    public void Landing_AcrossFourPhases_TakesTwoValues64ApartSplitByK(int k)
    {
        const int sphereOffset = 0x1C;
        uint[] anchors = Anchors(Scenes[0], Loads);

        int[] landings = [.. Enumerable.Range(8, 4).Select(origin => sphereOffset + (int)anchors[origin] - (int)anchors[origin + k])];

        int[] values = [.. landings.Distinct().Order()];
        Assert.Equal(2, values.Length);
        Assert.Equal(64, values[1] - values[0]);
        Assert.Equal(k % 4, landings.Count(landing => landing == values[0]));
    }

    [Theory]
    [InlineData(4)]
    [InlineData(8)]
    public void Landing_WhenKIsAMultipleOfFour_IsTheSameInEveryPhase(int k)
    {
        const int sphereOffset = 0x1C;
        uint[] anchors = Anchors(Scenes[0], Loads);

        int[] landings = [.. Enumerable.Range(8, 4).Select(origin => sphereOffset + (int)anchors[origin] - (int)anchors[origin + k])];

        Assert.Single(landings.Distinct());
    }
}
