Next slice:
Move the single-repo generation core into modules:

ccc/extractors/base.py
ccc/extractors/python.py
ccc/extractors/typescript.py
ccc/generators/tree.py
ccc/generators/schemas.py
ccc/generators/api.py
ccc/generators/dependencies.py
ccc/generators/symbols.py
ccc/generators/entrypoints.py
ccc/generators/database.py
ccc/generators/contracts.py
ccc/generators/scaffolds.py
Then wire ccc/generator.py to actually orchestrate them.

That is the point where the package becomes the real implementation rather than just the shell.
