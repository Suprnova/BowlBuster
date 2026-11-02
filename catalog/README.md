# BowlBuster Catalog

This directory holds the YAML files BowlBuster reads to classify and describe the effects of Bowl Storage writes: the rules, hypotheses, vocabulary, and types that say what the game does when the write lands on a given spot in memory.

## Files

- [`vocabulary.yaml`](vocabulary.yaml): the names of costumes, levels, worlds and task slots. The file's opening comment is the guide to adding or changing a name: its shape, the naming conventions and the rules a name must meet. `dotnet test` reads the file and reports every problem it finds.

## License

Everything in this directory is licensed under [CC0 1.0 Universal](../LICENSES/CC0-1.0.txt), which dedicates it to the public domain. This differs from the rest of BowlBuster, which is under the [MIT License](../LICENSE).
