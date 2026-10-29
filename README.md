# BowlBuster

BowlBuster is a tool for studying Bowl Storage, a memory-corruption glitch in *The SpongeBob SquarePants Movie* (Xbox, NTSC-U retail) caused by a dangling pointer write.

Leaving a scene within a second of a Macho Bowl explosion keeps the explosion's flag set through later scene changes, and from then on the player render writes through a pointer into an earlier scene's memory, which later scenes have since reused. Where that write lands, and so what it overwrites, depends on the scenes loaded in between, their order, the costumes worn, and how many loads came before. A run that controls those can complete tasks, warp through the pause menu to places it shouldn't reach, or crash the game.

BowlBuster predicts where each load's write lands, describes the effects of the landing, searches for chains of loads that reach a wanted effect, and checks its predictions by running them in the game.

## Status

BowlBuster is in early development.

## Building

BowlBuster needs the [.NET 10 SDK](https://dotnet.microsoft.com/download).

```
dotnet build
dotnet test
dotnet run --project src/BowlBuster.Cli
```

## License

BowlBuster's code is licensed under the [MIT License](LICENSE). The rule catalog in [catalog/](catalog/) is licensed under [CC0 1.0](LICENSES/CC0-1.0.txt).

Contributions are welcome under the terms of the [AI contributions policy](AI_POLICY.md).
