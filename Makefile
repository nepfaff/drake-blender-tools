.PHONY: sync-addon build-addon test clean

ADDON_DIR := blender_addons/meshcat_html_importer
PKG_SRC := packages/meshcat-html-importer/src/meshcat_html_importer

# Sync package code to addon directory.
# Copies subpackages (parser, scene, animation, blender) into the addon and
# converts absolute imports to relative imports for Blender 5.0 extension compliance.
sync-addon:
	@echo "Syncing package to addon..."
	rm -rf $(ADDON_DIR)/parser $(ADDON_DIR)/scene $(ADDON_DIR)/animation $(ADDON_DIR)/blender_impl $(ADDON_DIR)/_msgpack
	cp -r $(PKG_SRC)/parser $(ADDON_DIR)/
	cp -r $(PKG_SRC)/scene $(ADDON_DIR)/
	cp -r $(PKG_SRC)/animation $(ADDON_DIR)/
	cp -r $(PKG_SRC)/blender $(ADDON_DIR)/blender_impl
	cp -r $(PKG_SRC)/vendor/msgpack $(ADDON_DIR)/_msgpack
	@# Convert absolute imports to relative imports
	find $(ADDON_DIR)/parser -name '*.py' -exec perl -pi -e 's/from meshcat_html_importer\.parser\./from ./g' {} +
	find $(ADDON_DIR)/scene -name '*.py' -exec perl -pi -e 's/from meshcat_html_importer\.scene\./from ./g' {} +
	find $(ADDON_DIR)/animation -name '*.py' -exec perl -pi -e 's/from meshcat_html_importer\.animation\./from ./g' {} +
	find $(ADDON_DIR)/blender_impl -name '*.py' -exec perl -pi -e 's/from meshcat_html_importer\.blender\./from ./g' {} +
	@# Fix cross-package imports (e.g., scene -> parser, blender_impl -> scene)
	find $(ADDON_DIR) -name '*.py' -exec perl -pi -e 's/from meshcat_html_importer\.parser/from ..parser/g' {} +
	find $(ADDON_DIR) -name '*.py' -exec perl -pi -e 's/from meshcat_html_importer\.scene/from ..scene/g' {} +
	find $(ADDON_DIR) -name '*.py' -exec perl -pi -e 's/from meshcat_html_importer\.animation/from ..animation/g' {} +
	find $(ADDON_DIR) -name '*.py' -exec perl -pi -e 's/from meshcat_html_importer\.blender/from ..blender_impl/g' {} +
	@# Fix msgpack vendor import
	find $(ADDON_DIR)/parser -name '*.py' -exec perl -pi -e 's/from meshcat_html_importer\.vendor import msgpack/from .. import _msgpack as msgpack/g' {} +
	@# Remove fallback 'import msgpack' lines (only in try/except blocks)
	@echo "Done. Addon synced."

# Build addon zip for distribution
build-addon: sync-addon
	@echo "Building addon zip..."
	cd $(ADDON_DIR) && zip -r ../../meshcat_html_importer.zip . -x '*/__pycache__/*'
	@echo "Created meshcat_html_importer.zip"

# Run all tests
test:
	uv run pytest

# Clean build artifacts
clean:
	rm -f meshcat_html_importer.zip
