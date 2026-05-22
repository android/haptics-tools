#  Copyright 2026 Google LLC
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""Shared PyInstaller utilities for Haptics Tools."""

import sys


def exclude_glib_gio(analysis_obj):
  """Excludes GLib and GIO libraries from PyInstaller Analysis on Linux.

  This avoids ABI mismatch issues with host GVFS.

  Args:
    analysis_obj: The PyInstaller Analysis object to modify.

  Returns:
    The modified Analysis object.
  """
  if not sys.platform.startswith('linux'):
    return analysis_obj

  excluded_binaries = {
      'libglib-2.0.so',
      'libgio-2.0.so',
      'libgobject-2.0.so',
      'libgthread-2.0.so',
      'libgmodule-2.0.so',
  }

  print('--- PyInstaller Binary Exclusion Debug (Shared Helper) ---')

  # Filter binaries
  print('Before binaries filter:', len(analysis_obj.binaries))
  matching_binaries = [
      x[0]
      for x in analysis_obj.binaries
      if any(lib in x[0] for lib in excluded_binaries)
  ]
  print('Matching binaries to exclude:', matching_binaries)
  analysis_obj.binaries = [
      x
      for x in analysis_obj.binaries
      if not any(lib in x[0] for lib in excluded_binaries)
  ]
  print('After binaries filter:', len(analysis_obj.binaries))

  # Filter datas
  print('Before datas filter:', len(analysis_obj.datas))
  matching_datas = [
      x[0]
      for x in analysis_obj.datas
      if any(lib in x[0] for lib in excluded_binaries)
  ]
  print('Matching datas to exclude:', matching_datas)
  analysis_obj.datas = [
      x
      for x in analysis_obj.datas
      if not any(lib in x[0] for lib in excluded_binaries)
  ]
  print('After datas filter:', len(analysis_obj.datas))

  print('---------------------------------------------------------')

  return analysis_obj
