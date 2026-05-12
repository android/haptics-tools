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

"""Master entry point for PCM to PWLE Haptics Tools."""

import argparse

from pcm2pwle import converter
from pcm2pwle import visualizer


def main() -> None:
  parser = argparse.ArgumentParser(
      description='A toolkit for converting and visualizing haptics.',
      formatter_class=argparse.ArgumentDefaultsHelpFormatter,
  )
  subparsers = parser.add_subparsers(
      dest='command', required=True, help='Available commands'
  )

  # Add subparsers for each tool
  converter.add_parser(subparsers)
  visualizer.add_parser(subparsers)

  args = parser.parse_args()

  if args.command == 'convert':
    converter.run(args)
  elif args.command == 'visualize':
    visualizer.run(args)


if __name__ == '__main__':
  main()
