# PageMap — make targets for local development.
#
# This Makefile is intentionally narrow: it covers the workflows the
# Python pyproject / uv tooling does not already expose (notably the
# Pi package install).

.PHONY: help
help: ## Show this help.
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} /^[a-zA-Z_-]+:.*##/ {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: pi-install
pi-install: ## Install the Pi package globally (use force=1 to reinstall).
	@bash scripts/install-pi-package.sh $(if $(force),--force)

.PHONY: pi-install-local
pi-install-local: ## Install the Pi package into project settings (./.pi/settings.json).
	@bash scripts/install-pi-package.sh --project $(if $(force),--force)

.PHONY: pi-uninstall
pi-uninstall: ## Uninstall the Pi package (use clean=1 to also remove node_modules).
	@bash scripts/uninstall-pi-package.sh $(if $(clean),--clean)

.PHONY: pi-update
pi-update: ## Update the installed Pi package after code changes.
	@pi update --extensions pagemap-pi

.PHONY: pi-clean
pi-clean: ## Remove package node_modules/ and lockfile.
	@rm -rf pagemap-pi/node_modules pagemap-pi/package-lock.json