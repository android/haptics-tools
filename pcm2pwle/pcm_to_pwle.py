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
import json
import logging
import os
import time
from typing import Any, Dict

import numpy as np
from scipy.io import wavfile
import soundfile as sf

from pcm2pwle import beating_detection as bd
from pcm2pwle import common_utils
from pcm2pwle import control_point_extraction as cpe
from pcm2pwle import frequency_amplitude_extraction as fae
from pcm2pwle import primitive_detection as pd


def run_pcm_to_pwle_conversion(
    pcm_raw: np.ndarray, rate: int, haptic_type: str, args: argparse.Namespace
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

  jnd_multiple = (
      args.jnd_multiple
      if args.jnd_multiple >= 0
      else common_utils.JND_MULTIPLE
  )

  # control point extraction
  start_time = time.time()
  if beating_freqs is not None:
    control_points = bd.extract_beating_control_points(
        amp_envelope,
        freq_envelope,
        beating_freqs,
        rate,
        error_threshold=args.error_threshold,
        jnd_multiple=jnd_multiple,
    )
  else:
    control_points = cpe.extract_control_points(
        amp_envelope,
        freq_envelope,
        rate,
        error_threshold=args.error_threshold,
        jnd_multiple=jnd_multiple,
    )
  logging.info(
      'Time spent on control point extraction: %f seconds',
      time.time() - start_time,
  )

  # convert to PWLE format
  start_time = time.time()
  if haptic_type == 'advanced_pwle_haptic':
    pwle_points = common_utils.generate_advanced_pwle(control_points)
  elif haptic_type == 'basic_pwle_haptic':
    pwle_points = common_utils.generate_basic_pwle(
        control_points,
        freq_profile=tuple(map(float, args.freq_profile)),
    )
  else:
    raise ValueError('Invalid haptic type')
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


def generate_pwle_json(
    name: str,
    points: Sequence[Any],
    haptic_type: str,
    output_path: str,
    json_version: str = 'v0.1.0',
) -> Dict[str, Any]:
  """Generates a dictionary structured as the required PWLE JSON format.

  This method is subject to change once we finalized the PWLE based format for
  Android Haptics.

  Args:
      name: The name of the PWLE.
      points: A list of PWLE point objects representing the effect elements.
      haptic_type: The type string for the haptic object.
      output_path: the JSON string will be written to this file path.
      json_version: The version string for the JSON format.

  Returns:
      A Python dictionary ready to be converted to a JSON string.
  """
  element_array_dicts = [p.to_dict() for p in points[1:]]

  pwle_name = 'pwle_' + haptic_type.split('_')[0] + '_' + name.replace('-', '_')
  # Build the DTO (Data Transfer Object)
  if haptic_type == 'advanced_pwle_haptic':
    haptic_object_dto = {
        'type': haptic_type,
        'name': pwle_name,
        'initialFrequency': float(points[1].frequency),
        'elementArray': element_array_dicts,
    }
  elif haptic_type == 'basic_pwle_haptic':
    haptic_object_dto = {
        'type': haptic_type,
        'name': pwle_name,
        'initialSharpness': float(points[1].sharpness),
        'elementArray': element_array_dicts,
    }
  else:
    raise ValueError('Invalid haptic type')

  pwle_json_data = {
      'jsonVersion': json_version,
      'hapticObjectDTO': haptic_object_dto,
  }

  json_string = json.dumps(pwle_json_data, indent=4)

  with open(output_path, 'w') as f:
    f.write(json_string)
    print(f'Successfully wrote PWLE JSON to {output_path}')

  return pwle_json_data


def read_pcm_file(pcm_file_name: str) -> tuple[int, np.ndarray]:
  """Reads a PCM file and returns the sample rate and data."""
  if pcm_file_name.endswith('.wav'):
    with open(pcm_file_name, 'rb') as f:
      rate, data = wavfile.read(f)
      # Take the first channel if stereo
      if data.ndim > 1:
        data = data[:, 0]
      return rate, data
  elif pcm_file_name.endswith('.ogg'):
    with open(pcm_file_name, 'rb') as f:
      data, rate = sf.read(f)
      # Vibration data stored in the second channel.
      if data.ndim != 2 or data.shape[1] < 2:
        raise ValueError(
            'OGG file must have at least 2 channels for vibration data.'
        )
      data = data[:, 1]
      return rate, data
  else:
    raise ValueError(
        f'Unsupported file extension in {pcm_file_name}. Only .wav and .ogg'
        ' files are supported.'
    )


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument(
      'pcm_file_name', help='Input PCM file name (.wav or .ogg)'
  )
  parser.add_argument('output_file_name', help='Output PWLE JSON file name')
  parser.add_argument(
      '--haptic_type',
      default='basic_pwle_haptic',
      choices=['advanced_pwle_haptic', 'basic_pwle_haptic'],
      help='The type of haptic to generate.',
  )
  parser.add_argument(
      '--error_threshold',
      type=float,
      default=0.01,
      help='The error threshold for control point extraction.',
  )
  parser.add_argument(
      '--jnd_multiple',
      type=float,
      default=-1.0,
      help=(
          'The JND multiple for control point extraction. Use default value'
          ' when negative.'
      ),
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
      default=0.1,
      help='The amplitude ratio threshold for primitive detection.',
  )
  parser.add_argument(
      '--primitive_freq_threshold',
      type=float,
      default=50,
      help='The frequency threshold for primitive detection.',
  )
  parser.add_argument(
      '--freq_profile',
      nargs=3,
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
  args = parser.parse_args()

  logging.basicConfig(level=args.loglevel)
  pcm_file_name = args.pcm_file_name
  output_file_name = args.output_file_name
  haptic_type = args.haptic_type

  sample_rate, data = read_pcm_file(pcm_file_name)
  pwle_points = run_pcm_to_pwle_conversion(data, sample_rate, haptic_type, args)
  generate_pwle_json(
      os.path.splitext(os.path.basename(pcm_file_name))[0],
      pwle_points,
      haptic_type,
      output_file_name,
  )


if __name__ == '__main__':
  main()
