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

"""Utility functions for primitive detection and manipulation."""

import numpy as np
from pcm2pwle import common_utils


def detect_primitives(
    amp_envelope: np.ndarray,
    freq_envelope: np.ndarray,
    rate: int,
    pulse_to_neighbor_ratio: float = 5,
    amp_ratio_threshold: float = 0.05,
    primitive_freq_threshold: float = 100,
    min_neighbor_ms: float = 10,
) -> list[tuple[float, float]]:
  """Detects pulses within a signal using the signal's amplitude and frequency envelopes as inputs.

  Args:
    amp_envelope: Amplitude envelope of the signal.
    freq_envelope: Instantaneous frequency envelope of the signal.
    rate (int): Sampling rate of the signal.
    pulse_to_neighbor_ratio: The sensitivity threshold for detecting pulses. A
      pulse is detected if its magnitude is `pulse_to_neighbor_ratio` times
      greater than the minimum magnitude of its neighbors. Therefore, a larger
      value makes the detection less sensitive (fewer points), while a smaller
      value makes it more sensitive (more points). Defaults to 5.
    amp_ratio_threshold: The amplitudes of all points within a detected pulse
      must be higher than this threshold value multiplied by the maximum
      amplitude of the signal. Defaults to 0.1.
    primitive_freq_threshold: The frequencies of all points within a detected
      pulse must be higher than this frequency threshold value. Defaults to 50.
    min_neighbor_ms: The duration used to define the left and right neighboring
      regions of a detected pulse. Defaults to 10.

  Returns:
    A list of detected pulses. Each pulse is a tuple of (start_time, end_time)
    in ms.
  """
  time = np.array([i / rate * 1000 for i in range(len(amp_envelope))])
  amp = amp_envelope.copy()
  freq = freq_envelope.copy()
  amp[0] = 0
  freq[0] = 0
  amp_threshold = amp_ratio_threshold * amp.max()
  min_pulse_duration_ms = 2
  max_pulse_duration_ms = 20

  detected_pulses = []
  in_potential_pulse = False
  pulse_start_index = -1

  for i in range(len(amp)):
    if (amp[i] > amp_threshold) and (freq[i] > primitive_freq_threshold):
      if not in_potential_pulse:
        in_potential_pulse = True
        pulse_start_index = i
    else:
      if in_potential_pulse:
        in_potential_pulse = False
        pulse_end_index = i - 1

        start_time = time[pulse_start_index]
        end_time = time[pulse_end_index]

        # Check if the chunk duration is within the specified range
        duration_ms = end_time - start_time
        if min_pulse_duration_ms <= duration_ms <= max_pulse_duration_ms:
          pulse_mask = (time >= start_time) & (time <= end_time)
          pulse_left_mask = (time <= start_time) & (
              time >= max(0, start_time - min_neighbor_ms)
          )
          pulse_right_mask = (time >= end_time) & (
              time <= min(time[-1], end_time + min_neighbor_ms)
          )

          amp_max = amp[pulse_mask].max()
          amp_mean = amp[pulse_mask].mean()
          freq_max = freq[pulse_mask].max()
          amp_left_min = max(amp[pulse_left_mask].min(), 0)
          amp_left_mean = amp[pulse_left_mask].mean()
          amp_right_mean = amp[pulse_right_mask].mean()
          freq_left_min = max(freq[pulse_left_mask].min(), 0)
          amp_right_min = max(amp[pulse_right_mask].min(), 0)
          freq_right_min = max(freq[pulse_right_mask].min(), 0)

          # main detection rule
          if (
              (amp_left_min == 0)
              or (amp_max / amp_left_min > pulse_to_neighbor_ratio)
          ) and (
              (amp_right_min == 0)
              or (amp_max / amp_right_min > pulse_to_neighbor_ratio)
          ):
            if (
                (freq_left_min == 0)
                or (freq_max / freq_left_min > pulse_to_neighbor_ratio)
            ) or (
                (freq_right_min == 0)
                or (freq_max / freq_right_min > pulse_to_neighbor_ratio)
            ):
              if amp_mean > amp_left_mean and amp_mean > amp_right_mean:
                detected_pulses.append((start_time, end_time))

  return detected_pulses


def silence_pcm_at_primitives(
    pcm: np.ndarray, detected_primitives: list[tuple[float, float]], rate: int
) -> np.ndarray:
  """Silences the PCM at the detected primitives.

  Args:
    pcm: The PCM data.
    detected_primitives: The detected primitives.
    rate: The sampling rate of the PCM data.

  Returns:
    The modified PCM data with silence at the detected primitives.
  """
  modified_pcm = pcm.copy()

  for start_time, end_time in detected_primitives:
    start_sample = int(start_time / 1000 * rate)
    end_sample = int(end_time /1000 * rate)
    modified_pcm[start_sample:end_sample + 1] = 0

  chunks = common_utils.zero_out_low_amplitude_chunks(
      modified_pcm,
      rate,
      amplitude_threshold_fraction=0.05,
      duration_threshold_ms=20,
      amp_max=np.max(np.abs(pcm)),
  )
  for _, (start, end) in enumerate(chunks):
    modified_pcm[start:end] = 0.0

  return modified_pcm


def calculate_primitive_insert_points(
    pcm: np.ndarray, detected_primitives: list[tuple[float, float]], rate: int
) -> list[tuple[float, float]]:
  """Calculates the primitive insert points.

  Args:
    pcm: The PCM data.
    detected_primitives: The detected primitives.
    rate: The sampling rate of the PCM data.

  Returns:
    A list of primitive insert points. Each point is a tuple of (start_time,
    end_time) in ms.
  """

  primitive_insert_points = []

  for start_time, end_time in detected_primitives:
    start_sample = int(start_time / 1000 * rate)
    end_sample = int(end_time / 1000 * rate)
    pulse_value = pcm[start_sample : end_sample + 1]
    primitive_insert_points.append(
        (start_time, np.max(np.abs(pulse_value)) / np.max(np.abs(pcm)))
    )

  return primitive_insert_points
