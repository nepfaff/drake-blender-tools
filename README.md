# Drake Blender Tools

A monorepo containing tools for working with Drake simulations in Blender.

Allows you to easily record Drake simulations and import them into Blender for
visualization. The Blender scenes are animated using keyframes.

Note that part of the code is based on
[Drake Blender](https://github.com/RobotLocomotion/drake-blender).
This work was inspired by
[pybullet-blender-recorder](https://github.com/huy-ha/pybullet-blender-recorder).

Below is an example video from
[Steerable Scene Generation](https://steerable-scene-generation.github.io/) that was
enabled by Drake Blender Recorder. All individual clips from that video were created
by first simulating in Drake, exporting into Blender using Drake Blender Recorder, and
then rendering with Blender.

<a href="https://youtu.be/oh9RajpEjKw">
  <img src="media/steerable_scene_generation.png" alt="example_video" width="400">
</a>

## Packages

### [drake-recording-server](./packages/drake-recording-server/)

A Flask server that records Drake simulation states as Blender keyframes. It implements Drake's glTF Render Client-Server API but instead of rendering images, it saves object poses that can be imported into Blender.

```bash
drake-recording-server \
    --export_path output/scene.blend \
    --keyframe_dump_path output/keyframes.pkl
```

### [meshcat-html-importer](./packages/meshcat-html-importer/)

Import meshcat HTML recordings (saved from the meshcat web viewer) into Blender with full geometry, materials, and animation support.

**CLI usage** (requires `bpy` package):
```bash
meshcat-html-import recording.html -o scene.blend
```

**Blender addon** (recommended): File > Import > Meshcat Recording (.html) - see [addon installation](#meshcat-html-importer-blender_addonsmeshcat_html_importer) below.

## Blender Addons

### Keyframe Importer (`blender_addons/keyframe_importer.py`)

A Blender addon to import keyframe data from the recording server.

**Installation:**
1. Open Blender
2. Edit > Preferences > Add-ons
3. Click on the down arrow in the top right corner and select "Install from Disk..."
4. Select `blender_addons/keyframe_importer.py`
5. Enable the "Keyframe Importer" addon

![Blender Plugin Installation](media/blender_plugin_install.png)

![Blender Addon Enabled](media/blender_plugin_enabled.png)

You should see a "Keyframe Importer" entry in the sidebar.

![Blender Sidebar](media/blender_sidebar.png)

### Meshcat HTML Importer (`blender_addons/meshcat_html_importer/`)

A Blender extension to import meshcat HTML recordings directly.

**Installation (Blender 5.0+):**
1. Download `meshcat_html_importer.zip` from the [latest release](../../releases/latest), or build it locally with `make build-addon`
2. Open Blender
3. Edit > Preferences > Get Extensions
4. Click the dropdown arrow and select "Install from Disk..."
5. Select the `meshcat_html_importer.zip` file

**Usage:**
1. File > Import > Meshcat Recording (.html)
2. Select your meshcat HTML recording
3. Configure FPS and other options
4. Import

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for package management.

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all packages (including dev dependencies)
uv sync --extra dev

# Install workspace packages
uv pip install -e packages/drake-recording-server -e packages/meshcat-html-importer
```

## Workflow

### Recording Server Workflow

#### Recording from Drake Simulation

1. Start the recording server:
   ```bash
   drake-recording-server \
       --export_path examples/example_output/example.blend \
       --keyframe_dump_path examples/example_output/example.pkl \
       --blend_file examples/example_output/example_start.blend
   ```
   Note that you need to re-start the server whenever you want to start a new recording.

2. Run your simulation. Note that every render request from a Blender camera
   will trigger the recording of a new keyframe. The example simulation script shows
   how to set up such a camera:
   ```bash
   python examples/example_sim.py
   ```

3. Open the exported `.blend` file in Blender

4. Use the "Keyframe Importer" addon to import the `.pkl` file

![Blender Import](media/blender_pkl_import.png)

You can now play back the animation in Blender.

![Blender Playback](media/blender_imported_keyframes.gif)

#### Examples

We provide pre-recorded example files in `examples/example_output/` for testing.

The example is a simple iiwa teleop. It will open up a Meshcat window that can be used
for controlling the iiwa arm.

The final render might look something like this:

![Blender Playback](media/blender_playback.gif)

### Meshcat HTML Importer Workflow

1. Save your meshcat visualization as HTML (using the save button in meshcat viewer)

2. Import using either:
   - **Blender addon** (recommended): File > Import > Meshcat Recording (.html)
   - **CLI** (requires `bpy` package): `meshcat-html-import recording.html -o scene.blend`

## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Format code
uv run ruff format .

# Lint
uv run ruff check .
```

### Building the Blender Addon

The Blender addon's subpackages (`parser/`, `scene/`, `animation/`, `blender_impl/`) are synced from the `meshcat-html-importer` package source with absolute imports converted to relative imports (required by Blender 5.0's extension policy). After making changes to the package, sync and build the addon:

```bash
# Sync package code to addon and convert imports
make sync-addon

# Build addon zip for distribution
make build-addon

# Clean build artifacts
make clean
```

The `make build-addon` target creates `meshcat_html_importer.zip` which can be installed in Blender via Edit > Preferences > Get Extensions > Install from Disk.

### Releasing a New Version

Pushing a version tag triggers a GitHub Actions workflow that builds the addon zip and creates a GitHub Release with the zip attached.

```bash
git tag v0.1.0
git push origin v0.1.0
```
