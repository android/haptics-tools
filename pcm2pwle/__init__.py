#  Copyright 2026 Google LLC
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
"""PCM to PWLE Haptics Conversion and Visualization package."""

import os

# Force GIO to use local VFS to avoid ABI mismatch crashes with host system
# GVFS libraries when GLib/GIO are bundled in the standalone executable.
# Setting this at the package level ensures it runs before any submodules
# (which might load GUI libraries depending on GIO) are imported.
os.environ['GIO_USE_VFS'] = 'local'
