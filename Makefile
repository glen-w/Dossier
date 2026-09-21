# Dossier Makefile

.DEFAULT_GOAL := help

.PHONY: help docs docs-clean pages-site prove test

help:
	@echo "Dossier Makefile"
	@echo ""
	@echo "  docs         Build Sphinx HTML into docs/_build/html (requires .[docs])"
	@echo "  docs-clean   Remove Sphinx build artifacts"
	@echo "  pages-site   Assemble website/ + Sphinx guide into _site/"
	@echo "  prove        Disposable real-corpus pass (local; never approves)"
	@echo "  test         uv run pytest"
	@echo ""
	@echo "Usage: uv sync --extra docs && make docs"
	@echo "       make pages-site"
	@echo "       make prove"

docs:
	@bash scripts/release/build_docs.sh

docs-clean:
	@echo "Cleaning Sphinx build artifacts..."
	@rm -rf docs/_build _site
	@echo "Documentation build cleaned."

pages-site:
	@bash scripts/release/assemble_pages_site.sh

prove:
	@bash scripts/prove_0_6.sh

test:
	@uv run pytest
