# Changelog

Each release has a section; its text becomes the GitHub release notes and the Marketplace's
"what's new". New entries are fragments in `changelog.d/`: `python scripts/changelog.py collect`
adds them under `## [Unreleased]`, and `mason bump` turns that into the version.

## 1.0.2

- Shows its own icon in Floorbit's plugin list and Marketplace.

## 1.0.1

- Keeps reading for the whole event when a round goes wrong. Home Assistant answering something
  other than its list of states, something that isn't a web server at its address, or any other
  surprise, used to stop the reading until the agent restarted; now it is an error for that round.
- A sensor state of `nan` or `inf` is no reading.

## 1.0.0

- First release from its own repository. Until now the plugin shipped inside Floorbit; it works
  the same, and the local agents get it as the same signed file.
