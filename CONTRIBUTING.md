# Contributing

Thank you for looking. This is a small project in an early stage (version 0.x), so the rules are short.

## What we welcome

- **Issues.** Bugs, unclear docs, a result you cannot reproduce.
- **Failure reports.** A photo where onmodel's verdict was wrong, or where an engine failed in a way the rubric does not name. Use the template. Only share photos you have the right to share, and never photos of real people who have not agreed to it.
- **Engine adapters.** A class for another image engine, with a test. See [bring your engine](docs/bring-your-engine.md).
- **Small fixes** with a test.

## What we do not take yet

- **New images or recipes.** We cannot verify where an image comes from or whether a recipe was tuned on test photos, and either would weaken the benchmark. Open an issue to discuss; do not send a pull request with images.
- **Changes to the rubric** (the questions, the points, the veto codes). They change what every result means. Open an issue first.

## Set up

```bash
git clone https://github.com/molly554/onmodel
cd onmodel
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Before you open a pull request

Run what the CI runs. None of it needs a key or a network.

```bash
python scripts/sync_generated.py --check        # files generated from onmodel/taxonomy.py and the starter recipes
python scripts/check_assets.py                  # licenses, provenance, content and secrets
python scripts/check_links.py                   # links in the Markdown files
python scripts/recompute_mini_test.py --check   # the published mini-test numbers match their table
onmodel bench smoke                             # the whole pipeline, offline
pytest
```

If you change `onmodel/taxonomy.py` or `onmodel/data/starter-recipes.yaml`, run `python scripts/sync_generated.py` and commit the files it writes.

## Code

- Python 3.10 or newer. Keep the runtime dependencies to PyYAML and Pillow.
- The skills in `skills/` are standard-library only and carry their own copy of the scorer; a test keeps it identical to `onmodel/scoring.py`.
- Never print, log or write an API key. Keys come from the environment.
- Anything that costs money is a dry run unless `--yes` is given.

## Style of the docs

Plain sentences, sentence-case headings, no emoji, no exclamation marks. Say what was measured, how many, and what it cannot tell you.

## License

By contributing you agree that your contribution is licensed under the Apache License 2.0 (code) or CC BY 4.0 (docs and figures), as the file you change already is.
