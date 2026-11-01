"""hermes-gruvbox — the Gruvbox theme pack.

On load the pack installs its six skins into the active profile's
`<hermes home>/skins/`, the data the pack ships; a skin the user edited, or a
same-named file the pack did not write, is never touched, and loading never
switches the active skin.

The pack registers no commands. The themes are chosen in the Desktop app's own
picker, which `desktop/plugin.js` contributes them to.
"""

from __future__ import annotations

import subprocess

from .installer import ThemeError, install

_LOG = "hermes-gruvbox"


def _bootstrap() -> None:
    try:
        install()  # idempotent; a no-op once installed, and off after uninstall
    except (ThemeError, OSError, ValueError, subprocess.SubprocessError) as error:
        import logging

        logging.getLogger(_LOG).warning("could not install Gruvbox skins: %s", error)


def register(ctx):
    """Entry point: install the skins, register nothing else."""
    _bootstrap()
