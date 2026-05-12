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

"""A tool to convert PCM file to PWLE format."""

import argparse
from collections.abc import Sequence
import copy
import logging
import time
from typing import Any

import numpy as np

from pcm2pwle import beating_detection as bd
from pcm2pwle import common_utils
from pcm2pwle import control_point_extraction as cpe
from pcm2pwle import frequency_amplitude_extraction as fae
from pcm2pwle import primitive_detection as pd


def run_pcm_to_pwle_conversion(
    pcm_raw: np.ndarray, rate: int, pwle_type: str, args: argparse.Namespace
) -> Sequence[Any]:
  """Runs the PCM to PWLE conversion."""
  # data preprocess & freq/amp envelope extraction
  start_time = time.time()
  pcm_preprocessed = fae.vib_data_preprocess(
      pcm_raw,
      rate,
      preprocess_lowpass_cutoff=500,
      crop_s=args.crop_s if args.crop_s > 0 else None,
  )
  logging.info(
      'Time spent on vib_data_preprocess: %f seconds', time.time() - start_time
  )

  pcm_preprocessed_copy = copy.deepcopy(pcm_preprocessed)
  start_time = time.time()
  amp_envelope, freq_envelope = fae.extract_vib_amp_freq(
      pcm_preprocessed, rate, envelope_lowpass_cutoff=100
  )
  logging.info(
      'Time spent on extract_vib_amp_freq: %f seconds', time.time() - start_time
  )

  # primitive detection
  start_time = time.time()
  detected_primitives = pd.detect_primitives(
      amp_envelope,
      freq_envelope,
      rate,
      pulse_to_neighbor_ratio=args.pulse_to_neighbor_ratio,
      amp_ratio_threshold=args.amp_ratio_threshold,
      primitive_freq_threshold=args.primitive_freq_threshold,
  )
  logging.info(
      'Time spent on detect_primitives: %f seconds', time.time() - start_time
  )
  if detected_primitives:
    start_time = time.time()
    pcm_preprocessed = pd.silence_pcm_at_primitives(
        pcm_preprocessed, detected_primitives, rate
    )
    logging.info(
        'Time spent on silence_pcm_at_primitives: %f seconds',
        time.time() - start_time,
    )
    start_time = time.time()
    amp_envelope, freq_envelope = fae.extract_vib_amp_freq(
        pcm_preprocessed, rate, envelope_lowpass_cutoff=100
    )
    logging.info(
        'Time spent on extract_vib_amp_freq after silencing: %f seconds',
        time.time() - start_time,
    )

  # beating detection
  start_time = time.time()
  beating_freqs = bd.is_beating(pcm_raw, rate)
  logging.info('Time spent on is_beating: %f seconds', time.time() - start_time)

  # control point extraction
  start_time = time.time()
  if beating_freqs is not None:
    control_points = bd.extract_beating_control_points(
        amp_envelope,
        freq_envelope,
        beating_freqs,
        rate,
        pwle_type,
        error_threshold=args.error_threshold,
    )
  else:
    control_points = cpe.extract_control_points(
        amp_envelope,
        freq_envelope,
        rate,
        pwle_type,
    )
  logging.info(
      'Time spent on control point extraction: %f seconds',
      time.time() - start_time,
  )

  # convert to PWLE format
  start_time = time.time()
  if pwle_type == 'advanced_pwle':
    pwle_points = common_utils.generate_advanced_pwle(control_points)
  elif pwle_type == 'basic_pwle':
    pwle_points = common_utils.generate_basic_pwle(
        control_points,
        freq_profile=tuple(map(float, args.freq_profile)),
    )
  else:
    raise ValueError('Invalid PWLE type')
  logging.info(
      'Time spent on PWLE generation: %f seconds', time.time() - start_time
  )

  # TODO: Add primitive insert points to the PWLE when
  # PWLE / primitive composition is ready.
  # primitive insert point calculation
  start_time = time.time()
  primitive_insert_points = pd.calculate_primitive_insert_points(
      pcm_preprocessed_copy, detected_primitives, rate
  )
  logging.info(
      'Time spent on calculate_primitive_insert_points: %f seconds',
      time.time() - start_time,
  )

  return pwle_points


class _HelpFormatter(
    argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter
):
  pass


def add_parser(subparsers: argparse._SubParsersAction) -> None:
  """Adds the convert subcommand to the main parser."""
  description = (
      'Convert raw haptic PCM data (.wav or .ogg) into the PWLE XML format.\n\n'
      'This tool analyzes the input haptic waveform and generates a nearly\n'
      'equivalent Piecewise Linear Envelope (PWLE) representation, which is\n'
      'then saved to the specified output file.'
  )
  parser = subparsers.add_parser(
      'convert',
      help='Convert PCM to PWLE format.',
      description=description,
      formatter_class=_HelpFormatter,
  )
  parser.add_argument(
      '--pcm', required=True, help='Path to input PCM file (.wav or .ogg)'
  )
  parser.add_argument(
      '--output', required=True, help='Path to output PWLE XML file'
  )
  parser.add_argument(
      '--pwle_type',
      default='basic_pwle',
      choices=['advanced_pwle', 'basic_pwle'],
      help='The type of haptic to generate.',
  )
  parser.add_argument(
      '--error_threshold',
      type=float,
      default=0.01,
      help='The error threshold for control point extraction.',
  )
  parser.add_argument(
      '--pulse_to_neighbor_ratio',
      type=float,
      default=5,
      help='The pulse to neighbor ratio for primitive detection.',
  )
  parser.add_argument(
      '--amp_ratio_threshold',
      type=float,
      default=0.05,
      help='The amplitude ratio threshold for primitive detection.',
  )
  parser.add_argument(
      '--primitive_freq_threshold',
      type=float,
      default=100,
      help='The frequency threshold for primitive detection.',
  )
  parser.add_argument(
      '--freq_profile',
      nargs=3,
      metavar=('LOW', 'RES', 'HIGH'),
      default=['50', '136', '174'],
      help='The frequency profile for basic PWLE generation.',
  )
  parser.add_argument(
      '--crop_s',
      type=float,
      default=-1,
      help=(
          'The number of seconds to crop from the beginning of the PCM data.'
          ' Do not crop when non-positive.'
      ),
  )
  parser.add_argument(
      '--loglevel',
      default='WARNING',
      choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
      help='Set the logging level.',
  )


def run(args: argparse.Namespace) -> None:
  """Executes the conversion logic."""
  logging.basicConfig(level=args.loglevel)
  pcm_file_name = args.pcm
  output_file_name = args.output
  pwle_type = args.pwle_type

  data, sample_rate = common_utils.load_pcm_file(pcm_file_name)
  pwle_points = run_pcm_to_pwle_conversion(data, sample_rate, pwle_type, args)
  common_utils.generate_pwle_xml(
      pwle_points,
      pwle_type,
      output_file_name,
      xml_version='2.0',
  )
