using BowlBuster.Landings;
using BowlBuster.Memory;
using BowlBuster.Recordings;

namespace BowlBuster.Tests.Landings;

public class LoadContextTests
{
    [Fact]
    public void Of_ALoadsRequests_ListsTheArchivesOfItsLayersOnceInOrder()
    {
        HeapLog heap = new(
            new HeapSnapshot([new HeapState(0x100000, 0, 0)], null),
            [
                new AllocRequest(0x800, 0x40, 0x100000, 0x192860, new LayerId("B1\\B101.HOP", 0)),
                new AllocRequest(0x60, 0x10, 0x100800, 0x192860),
                new AllocRequest(0x800, 0x40, 0x100880, 0x192860, new LayerId("B1\\B101", 0)),
                new AllocRequest(0x800, 0x40, 0x101080, 0x192860, new LayerId("B1\\B101.HOP", 1)),
            ],
            null,
            false);

        LoadContext context = LoadContext.Of(heap, null);

        Assert.Equal(["B1\\B101.HOP", "B1\\B101"], context.Archives);
    }
}
