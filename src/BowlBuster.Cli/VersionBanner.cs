using System.Reflection;

namespace BowlBuster.Cli;

internal static class VersionBanner
{
    public static string For(Assembly assembly)
    {
        AssemblyName name = assembly.GetName();
        return $"{name.Name} {name.Version}";
    }
}
