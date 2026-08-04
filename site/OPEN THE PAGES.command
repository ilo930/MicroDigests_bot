#!/bin/bash
# Double-click this in Finder. It opens the version chooser in your browser.
# The pages are plain files: no server, no terminal, nothing to install.
open "$(cd "$(dirname "$0")" && pwd)/versions/index.html"
