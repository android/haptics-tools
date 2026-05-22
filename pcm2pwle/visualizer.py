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

"""A tool to visualize PCM and XML data."""

import argparse
import os
import sys
from typing import Any, Dict, List

import numpy as np

from pcm2pwle import common_utils

# Styling constants
TEXT_COLOR = '#333333'


PRESET_SPECS = {
    'TICK': {
        'duration_ms': 5,
        'freq_factor': 3.0,
        'intensity_factor': 0.5,
        'color': 'tab:orange',
    },
    'LOW_TICK': {
        'duration_ms': 12,
        'freq_factor': 2.0 / 3.0,
        'intensity_factor': 0.125,
        'color': 'tab:brown',
    },
    'CLICK': {
        'duration_ms': 12,
        'freq_factor': 1.0,
        'intensity_factor': 1.0,
        'color': 'tab:purple',
    },
}


def generate_pcm_from_points(
    points: List[Dict[str, Any]],
    sample_rate: int,
    pwle_type: str,
    presets: List[Dict[str, Any]] | None = None,
) -> np.ndarray:
  """Generates a PCM waveform from PWLE points and presets."""
  # If the haptic pattern starts with a silent period (e.g. envelopes start
  # after 0ms), we pad the beginning of the generated samples list with zero
  # amplitude silence. This preserves the correct absolute length and timing
  # alignment of the reconstructed PCM without requiring any artificial starting
  # points to be inserted into the XML or plotted envelopes.
  samples = []
  if points and points[0]['time'] > 0:
    silent_samples_count = int(sample_rate * points[0]['time'] / 1000)
    samples = [0.0] * silent_samples_count

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

  samples_arr = np.array(samples)

  if presets:
    # Using the resonant frequency from the default profile.
    base_resonant_freq = common_utils.PWLE_FREQ_PROFILE[1]

    for preset in presets:
      enum_val = preset['presetEnum']

      # Default to CLICK if unknown.
      spec = PRESET_SPECS.get(enum_val, PRESET_SPECS['CLICK'])

      duration_ms = spec['duration_ms']
      freq = base_resonant_freq * spec['freq_factor']
      intensity = preset['intensity'] * spec.get('intensity_factor', 1.0)

      start_sample = int(preset['time'] / 1000 * sample_rate)
      burst_len = int(duration_ms / 1000 * sample_rate)
      end_sample = start_sample + burst_len

      if end_sample > len(samples_arr):
        samples_arr = np.pad(samples_arr, (0, end_sample - len(samples_arr)))

      t = np.arange(burst_len) / sample_rate

      # To ensure symmetric amplitude visualization, we use a Tukey window
      # (flat in the middle) and center the sine wave so that zero-crossings
      # are balanced.
      # We aim for at least one full symmetric swing [-1, 1].
      phase_offset = -np.pi * freq * (duration_ms / 1000.0)
      burst = intensity * np.sin(2 * np.pi * freq * t + phase_offset)

      # Use a Tukey window with alpha=0.5 (flat for the middle 50%)
      # This allows both positive and negative peaks to reach full intensity.
      alpha = 0.5
      n = np.arange(burst_len)
      window = np.ones(burst_len)
      # Fade in
      width = int(alpha * burst_len / 2)
      if width > 0:
        window[:width] = 0.5 * (1 + np.cos(np.pi * (n[:width] - width) / width))
        # Fade out
        window[-width:] = 0.5 * (
            1 + np.cos(np.pi * (n[-width:] - (burst_len - 1 - width)) / width)
        )

      burst = burst * window

      # Add the burst to the reconstructed signal (overwrite to represent
      # preset overriding envelope)
      samples_arr[start_sample:end_sample] = burst

  return samples_arr


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
      '  --xml only          : Plots Haptics XML & reconstructed PCM'
      '                        interactively.\n'
      '  --pcm + --xml       : Plots raw PCM, Haptics XML, & reconstructed'
      '                        PCM.\n'
      '  ... + --output FILE : Saves the plot to the specified file (e.g.,'
      '                        .png, .pdf, .jpg) instead of opening an'
      '                        interactive window.\n'
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
  parser.add_argument(
      '--crop_s',
      type=float,
      default=-1,
      help=(
          'The number of seconds to show from the beginning of the data.'
          ' Do not crop when non-positive.'
      ),
  )


def run(args: argparse.Namespace) -> None:
  """Executes the visualizer logic."""
  if args.output:
    try:
      import matplotlib

      matplotlib.use('Agg')
    except ImportError:
      pass

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

  envelopes = None
  pwle_type = None
  presets = None
  pcm_reconstructed = None
  if args.xml:
    envelopes, pwle_type, presets = common_utils.parse_haptics_xml(args.xml)
    # Flatten the list of envelope segments into a single flat points list
    # for the PCM generator using clean extending loops
    flat_points = []
    if envelopes:
      for env in envelopes:
        flat_points.extend(env)
    pcm_reconstructed = generate_pcm_from_points(
        flat_points, sample_rate, pwle_type, presets
    )

  num_plots = 0
  if pcm_raw is not None:
    num_plots += 1
  if envelopes or presets:
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

    # Only crop the raw PCM if requested
    if args.crop_s > 0:
      crop_samples = int(args.crop_s * rate_raw)
      t_raw = t_raw[:crop_samples]
      pcm_raw = pcm_raw[:crop_samples]

    axes[curr_ax].plot(t_raw, pcm_raw, label='Raw PCM', color='blue', alpha=0.7)
    axes[curr_ax].set_ylabel('Amplitude', color=TEXT_COLOR)
    axes[curr_ax].legend()
    axes[curr_ax].set_title(
        f'Raw PCM Data (sample_rate={rate_raw} Hz)', color=TEXT_COLOR)
    axes[curr_ax].tick_params(colors=TEXT_COLOR)
    curr_ax += 1

  # 2. Haptics XML (Envelopes & Presets)
  if envelopes or presets:
    is_advanced = pwle_type == 'advanced_pwle' if pwle_type else False
    label1 = 'Amplitude' if is_advanced else 'Intensity'
    label2 = 'Frequency (Hz)' if is_advanced else 'Sharpness'

    # Draw envelope curves if present
    if envelopes:
      ax_twin = axes[curr_ax].twinx()
      for env_idx, env_points in enumerate(envelopes):
        times = [p['time'] / 1000 for p in env_points]
        if is_advanced:
          primary_envelope_values = [p['amplitude'] for p in env_points]
          secondary_envelope_values = [p['frequency'] for p in env_points]
        else:
          primary_envelope_values = [p['intensity'] for p in env_points]
          secondary_envelope_values = [p['sharpness'] for p in env_points]

        lbl1 = label1 if env_idx == 0 else ''
        lbl2 = label2 if env_idx == 0 else ''

        axes[curr_ax].plot(
            times, primary_envelope_values, label=lbl1, color='red', marker='o'
        )
        ax_twin.plot(
            times, secondary_envelope_values, label=lbl2, color='green',
            marker='x'
        )
      ax_twin.tick_params(colors=TEXT_COLOR)
      ax_twin.set_ylabel(label2, color=TEXT_COLOR)
    else:
      # Setup a dummy y-axis scale to cleanly host the presets
      axes[curr_ax].set_ylim(0, 1.1)

    # Draw preset events (bars)
    if presets:
      import matplotlib.patches as patches
      added_to_legend = set()
      for preset in presets:
        enum_val = preset['presetEnum']
        # Default to CLICK if unknown.
        spec = PRESET_SPECS.get(enum_val, PRESET_SPECS['CLICK'])
        duration_s = spec['duration_ms'] / 1000.0
        color = spec['color']
        preset_time = preset['time'] / 1000
        preset_intensity = preset['intensity'] * spec.get(
            'intensity_factor', 1.0
        )

        label = enum_val if enum_val not in added_to_legend else ''
        rect = patches.Rectangle(
            (preset_time, 0),
            duration_s,
            preset_intensity,
            linewidth=1,
            edgecolor=color,
            facecolor=color,
            alpha=0.5,
            label=label,
        )
        axes[curr_ax].add_patch(rect)
        added_to_legend.add(enum_val)

    axes[curr_ax].set_ylabel(label1, color=TEXT_COLOR)
    axes[curr_ax].tick_params(colors=TEXT_COLOR)

    # Construct the title dynamically based on parsed components
    title_parts = []
    if pwle_type:
      title_parts.append(pwle_type)
    if presets:
      title_parts.append('presets' if pwle_type else 'presets only')
    title_suffix = f" ({', '.join(title_parts)})" if title_parts else ''
    axes[curr_ax].set_title(f"Haptics XML{title_suffix}", color=TEXT_COLOR)

    # Compile and sort the legend based on a strict rank hierarchy:
    # Envelope: amplitude/intensity > frequency/sharpness
    # Preset: TICK > LOW_TICK > CLICK
    legend_ranks = {
        'Intensity': 1,
        'Amplitude': 1,
        'Sharpness': 2,
        'Frequency (Hz)': 2,
        'TICK': 3,
        'LOW_TICK': 4,
        'CLICK': 5,
    }

    lines, labels = axes[curr_ax].get_legend_handles_labels()
    if envelopes:
      lines2, labels2 = ax_twin.get_legend_handles_labels()
      all_handles = lines + lines2
      all_labels = labels + labels2
    else:
      all_handles = lines
      all_labels = labels

    # Zip and sort legend elements based on the rank mapping
    sorted_legend = sorted(
        zip(all_handles, all_labels),
        key=lambda x: legend_ranks.get(x[1], 99),
    )
    sorted_handles, sorted_labels = (
        zip(*sorted_legend) if sorted_legend else ([], [])
    )

    axes[curr_ax].legend(sorted_handles, sorted_labels, loc='best')

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
        'Reconstructed PCM from Haptics XML'
        f' (sample_rate={sample_rate} Hz)',
        color=TEXT_COLOR,
    )
    axes[curr_ax].tick_params(colors=TEXT_COLOR)
    curr_ax += 1

  plt.tight_layout()
  # Ensure y-axis labels are aligned across plots
  fig.align_ylabels(axes)

  if args.output:
    plt.savefig(args.output)
    print(f'Plot saved to {args.output}')
    plt.close(fig)
    plt.close('all')
  else:
    try:
      plt.show()
      plt.close('all')
    except Exception as e:
      print(f'Could not show plot: {e}. Use --output to save to a file.')


