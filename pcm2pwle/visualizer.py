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

r"""A tool to visualize PCM and XML data.

Usage:
  `--pcm` only:
    Raw PCM data will be plotted in an interactive window.
  `--xml` only:
    PWLE points and reconstructed waveform will be plotted in an interactive
    window.
  `--pcm` + `--xml`:
    Raw PCM, PWLE points, and reconstructed waveform will be plotted in an
    interactive window.
  Any of above + `--output`:
    Same as above, but the plot will be saved to the specified file (PNG, PDF,
    or JPG format).
"""

import argparse
import os
import sys
from typing import Any, Dict, List

import numpy as np

from pcm2pwle import common_utils

# Styling constants
TEXT_COLOR = '#333333'


def generate_pcm_from_points(
    points: List[Dict[str, Any]], sample_rate: int, pwle_type: str
) -> np.ndarray:
  """Generates a PCM waveform from PWLE points."""
  samples = []
  phase = 0.0
  is_advanced = pwle_type == 'advanced_pwle'

  for i in range(len(points) - 1):
    start = points[i]
    end = points[i + 1]

    duration_ms = end['time'] - start['time']
    if duration_ms <= 0:
      continue

    if is_advanced:
      a_start = start['amplitude']
      a_end = end['amplitude']
      f_start = start['frequency']
      f_end = end['frequency']
    else:
      a_start = start['intensity']
      a_end = end['intensity']
      f_start = common_utils.sharpness_to_freq(start['sharpness'])
      f_end = common_utils.sharpness_to_freq(end['sharpness'])

    segment_length = int(sample_rate * duration_ms / 1000)
    for j in range(segment_length):
      a = a_start + (a_end - a_start) * j / segment_length
      f = f_start + (f_end - f_start) * j / segment_length
      phase_delta = 2 * np.pi * f / sample_rate
      samples.append(a * np.sin(phase))
      phase += phase_delta
  return np.array(samples)


class _HelpFormatter(
    argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter
):
  pass


def add_parser(subparsers: argparse._SubParsersAction) -> None:
  """Adds the visualize subcommand to the main parser."""
  description = (
      'Visualize PCM and XML data.\n\n'
      'Behavior based on provided arguments:\n'
      '  --pcm only          : Plots the raw PCM data interactively.\n'
      '  --xml only          : Plots PWLE points & reconstructed PCM interactively.\n'
      '  --pcm + --xml       : Plots raw PCM, PWLE points, & reconstructed PCM.\n'
      '  ... + --output FILE : Saves the plot to the specified file (e.g., .png,\n'
      '                        .pdf, .jpg) instead of opening an interactive window.'
  )
  parser = subparsers.add_parser(
      'visualize',
      help='Visualize PCM and PWLE data.',
      description=description,
      formatter_class=_HelpFormatter,
  )
  parser.add_argument('--pcm', type=str, help='Path to raw PCM file (wav/ogg).')
  parser.add_argument('--xml', type=str, help='Path to XML file.')
  parser.add_argument(
      '--output', type=str, help='Path to save the plot (optional).'
  )
  parser.add_argument(
      '--sample_rate',
      type=int,
      default=None,
      help=('Sample rate for reconstruction. If not specified, it will be '
            'auto-detected from the --pcm file. If no --pcm file is provided, '
            'it defaults to 48000 Hz.'),
  )


def run(args: argparse.Namespace) -> None:
  """Executes the visualizer logic."""
  import matplotlib.pyplot as plt

  if not args.pcm and not args.xml:
    print('Error: Must provide --pcm or --xml for visualization.')
    sys.exit(1)

  # Resolve output path
  if args.output and not os.path.isabs(args.output):
    out_dir = os.path.dirname(os.path.abspath(args.output)) or '.'
    os.makedirs(out_dir, exist_ok=True)

  pcm_raw = None
  rate_raw = None
  if args.pcm:
    pcm_raw, rate_raw = common_utils.load_pcm_file(args.pcm)

  # Determine sample rate for reconstruction
  sample_rate = args.sample_rate
  if sample_rate is None:
    if rate_raw is not None:
      sample_rate = rate_raw
    else:
      sample_rate = 48000  # Default fallback

  pwle_points = None
  pwle_type = None
  pcm_reconstructed = None
  if args.xml:
    pwle_points, pwle_type = common_utils.parse_pwle_xml(args.xml)
    pcm_reconstructed = generate_pcm_from_points(
        pwle_points, sample_rate, pwle_type
    )

  num_plots = 0
  if pcm_raw is not None:
    num_plots += 1
  if pwle_points is not None:
    num_plots += 1
  if pcm_reconstructed is not None:
    num_plots += 1

  if num_plots == 0:
    print('Nothing to plot.')
    return

  fig, axes = plt.subplots(
      num_plots, 1, figsize=(12, 4 * num_plots), sharex=True
  )
  if num_plots == 1:
    axes = [axes]

  curr_ax = 0

  # 1. Raw PCM
  if pcm_raw is not None:
    t_raw = np.arange(len(pcm_raw)) / rate_raw
    axes[curr_ax].plot(t_raw, pcm_raw, label='Raw PCM', color='blue', alpha=0.7)
    axes[curr_ax].set_ylabel('Amplitude', color=TEXT_COLOR)
    axes[curr_ax].legend()
    axes[curr_ax].set_title(
        f'Raw PCM Data (sample_rate={rate_raw} Hz)', color=TEXT_COLOR)
    axes[curr_ax].tick_params(colors=TEXT_COLOR)
    curr_ax += 1

  # 2. PWLE Points
  if pwle_points is not None:
    times = [p['time'] / 1000 for p in pwle_points]
    is_advanced = pwle_type == 'advanced_pwle'

    if is_advanced:
      val1 = [p['amplitude'] for p in pwle_points]
      val2 = [p['frequency'] for p in pwle_points]
      label1 = 'Amplitude'
      label2 = 'Frequency (Hz)'
    else:
      val1 = [p['intensity'] for p in pwle_points]
      val2 = [p['sharpness'] for p in pwle_points]
      label1 = 'Intensity'
      label2 = 'Sharpness'

    ax_twin = axes[curr_ax].twinx()
    axes[curr_ax].plot(times, val1, label=label1, color='red', marker='o')
    ax_twin.plot(times, val2, label=label2, color='green', marker='x')

    axes[curr_ax].set_ylabel(label1, color=TEXT_COLOR)
    ax_twin.set_ylabel(label2, color=TEXT_COLOR)
    axes[curr_ax].set_title(
        f'PWLE Control Points ({pwle_type})', color=TEXT_COLOR)
    axes[curr_ax].tick_params(colors=TEXT_COLOR)
    ax_twin.tick_params(colors=TEXT_COLOR)

    # Combine legends
    lines, labels = axes[curr_ax].get_legend_handles_labels()
    lines2, labels2 = ax_twin.get_legend_handles_labels()
    axes[curr_ax].legend(lines + lines2, labels + labels2, loc='upper right')
    curr_ax += 1

  # 3. Reconstructed PCM
  if pcm_reconstructed is not None:
    t_recon = np.arange(len(pcm_reconstructed)) / sample_rate
    axes[curr_ax].plot(
        t_recon, pcm_reconstructed, label='Reconstructed PCM', color='orange'
    )
    axes[curr_ax].set_ylabel('Amplitude', color=TEXT_COLOR)
    axes[curr_ax].set_xlabel('Time (s)', color=TEXT_COLOR)
    axes[curr_ax].legend()
    axes[curr_ax].set_title(
        f'Reconstructed PCM from PWLE (sample_rate={sample_rate} Hz)',
        color=TEXT_COLOR)
    axes[curr_ax].tick_params(colors=TEXT_COLOR)
    curr_ax += 1

  plt.tight_layout()
  # Ensure y-axis labels are aligned across plots
  fig.align_ylabels(axes)

  if args.output:
    plt.savefig(args.output)
    print(f'Plot saved to {args.output}')
  else:
    try:
      plt.show()
    except Exception as e:
      print(f'Could not show plot: {e}. Use --output to save to a file.')


