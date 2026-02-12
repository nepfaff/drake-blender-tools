# Drake Blender Tools

Tools for importing [Drake](https://drake.mit.edu/) simulations into Blender. Record your simulations with [meshcat](https://github.com/meshcat-dev/meshcat) and import them into Blender with full geometry, materials, and animation support.

All Blender videos on [SceneSmith](https://scenesmith.github.io/) were created with the meshcat HTML importer.

<a href="https://youtu.be/oh9RajpEjKw">
  <img src="media/steerable_scene_generation.png" alt="example_video" width="400">
</a>

## Meshcat HTML Importer

### Installation (Blender 5.0+)

1. Download `meshcat_html_importer.zip` from the [latest release](../../releases/latest)
2. Open Blender
3. Edit > Preferences > Get Extensions
4. Click the dropdown arrow and select "Install from Disk..."
5. Select the `meshcat_html_importer.zip` file

### Usage

1. Save your meshcat visualization as HTML
2. Import into Blender using one of:
   - **File > Import > Meshcat Recording (.html)**
   - **Drag and drop** the `.html` file directly onto the Blender viewport
3. Configure import options and import

### Import Options

| Option | Description | Default |
|---|---|---|
| Recording FPS | FPS of the recording (0 = auto-detect) | 0 (auto) |
| Target FPS | Animation FPS in Blender | 30 |
| Start Frame | First frame number | 0 |
| Clear Scene | Remove existing objects before import | On |
| Hierarchical Collections | Create nested collections mirroring the meshcat scene tree | On |

### CLI Usage

For headless or scripted workflows (requires the `bpy` package). If you've set up the [development environment](#development), the CLI is already available:

```bash
meshcat-html-import recording.html -o scene.blend
```

## Development

This project uses [uv](https://github.com/astral-sh/uv) for package management.

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all packages with dev dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Format and lint
uv run ruff format .
uv run ruff check --fix .
```

### Building the Blender Addon

The addon source lives in `packages/meshcat-html-importer/src/` and is synced to `blender_addons/meshcat_html_importer/` with absolute imports converted to relative imports (required by Blender 5.0's extension policy). After making changes to the package:

```bash
# Sync package code to addon and convert imports
make sync-addon

# Build addon zip for distribution
make build-addon
```

### Releasing a New Version

Pushing a version tag triggers a GitHub Actions workflow that builds the addon zip and creates a GitHub Release with the zip attached.

```bash
git tag v0.1.0
git push origin v0.1.0
```

## Legacy: Drake Recording Server

An older workflow that records Drake simulations via a Flask server implementing Drake's glTF Render Client-Server API. Instead of rendering images, it saves object poses as keyframes that can be imported into Blender.

See the [drake-recording-server package](./packages/drake-recording-server/) for full documentation.

### Setup

```bash
uv pip install -e packages/drake-recording-server
```

### Workflow

1. Start the recording server:
   ```bash
   drake-recording-server \
       --export_path examples/example_output/example.blend \
       --keyframe_dump_path examples/example_output/example.pkl \
       --blend_file examples/example_output/example_start.blend
   ```
   Note that you need to re-start the server whenever you want to start a new recording.

2. Run your simulation. Every render request from a Blender camera triggers the recording of a new keyframe:
   ```bash
   python examples/example_sim.py
   ```

3. Open the exported `.blend` file in Blender

4. Install the Keyframe Importer addon (`blender_addons/keyframe_importer.py`) via Edit > Preferences > Add-ons > Install from Disk

5. Use the "Keyframe Importer" sidebar panel to import the `.pkl` file

![Blender Import](media/blender_pkl_import.png)

![Blender Playback](media/blender_imported_keyframes.gif)

Pre-recorded example files are provided in `examples/example_output/` for testing without a running Drake simulation.

## Acknowledgements

Part of the code is based on [Drake Blender](https://github.com/RobotLocomotion/drake-blender). This work was inspired by [pybullet-blender-recorder](https://github.com/huy-ha/pybullet-blender-recorder).
