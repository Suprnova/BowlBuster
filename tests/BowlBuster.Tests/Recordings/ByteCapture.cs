using BowlBuster.Recordings;
using System.Buffers.Binary;

namespace BowlBuster.Tests.Recordings;

/// <summary>
/// A capture of invented bytes from <paramref name="start"/>, which a test writes words and bytes into.
/// </summary>
internal sealed class ByteCapture(uint start, uint length) : ILoadCapture
{
    private readonly byte[] bytes = new byte[length];

    public uint HeapTop => start + (uint)bytes.Length;

    public ByteCapture Byte(uint address, byte value)
    {
        bytes[address - start] = value;
        return this;
    }

    public ByteCapture Word(uint address, uint value)
    {
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan((int)(address - start)), value);
        return this;
    }

    public bool TryRead(uint address, Span<byte> destination)
    {
        if (address < start || address + (uint)destination.Length > HeapTop) return false;

        bytes.AsSpan((int)(address - start), destination.Length).CopyTo(destination);
        return true;
    }
}
