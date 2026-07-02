# PageMap — make targets for local development.
#
# This Makefile is intentionally narrow: it covers the workflows the
# Python pyproject / uv tooling does not already expose (notably the
# Pi extension install).

.PHONY: help
help: ## Show this help.
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} /^[a-zA-Z_-]+:.*##/ {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: pi-install
pi-install: ## Symlink .pi/extensions/pagemap into ~/.pi/agent/extensions/ (use force=1 to replace).
	@bash scripts/install-pi-extension.sh $$( [ -n "$${force-}" ] && echo --force )

.PHONY: pi-uninstall
pi-uninstall: ## Remove the symlink from ~/.pi/agent/extensions/pagemap.
	@bash scripts/uninstall-pi-extension.sh
