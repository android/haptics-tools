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

"""Extract frequency and amplitude envelope, and control points from the vibration data."""

import copy
import logging

import numpy as np
import pandas as pd
from scipy import signal

from pcm2pwle import common_utils


def vib_data_preprocess(
    data: np.ndarray,
    rate: int,
    preprocess_lowpass_cutoff: int = 500,
    crop_s: float | None = None,
) -> np.ndarray:
  """Preprocess the vibration data.

  Args:
    data: The vibration data.
    rate: The sampling rate of the data.
    preprocess_lowpass_cutoff: The lowpass cutoff frequency for the data.
    crop_s: The duration seconds to keep from the start of the signal. Default
      is None (no cropping). Sometimes the signals can be very long to do the
      conversion. This allows users to cut the signal before analysis.

  Returns:
    The preprocessed vibration data.
  """
  data = copy.deepcopy(data)

  # Remove high freq noise
  if preprocess_lowpass_cutoff is not None:
    b, a = signal.butter(5, preprocess_lowpass_cutoff / (rate / 2), btype='low')
    data = signal.filtfilt(b, a, data)

  # Crop the data to keep only the first crop_s seconds
  if crop_s is not None:
    end_idx = np.min((len(data), int(crop_s * rate)))
    data = data[:end_idx]

  # Normalize data to [-1, 1]
  max_abs_data = np.max(np.abs(data))
  if max_abs_data > 0:
    data = data / max_abs_data

  return data


def _calculate_freq_env(
    data: np.ndarray,
    rate: int,
    envelope_lowpass_cutoff: float = 100
):
  """Calculates the frequency envelope of the vibration data."""
  analytic_signal = signal.hilbert(data)
  amp_envelope_raw = np.abs(analytic_signal)
  ins_phase = np.unwrap(np.angle(analytic_signal))
  freq_envelope_raw = np.diff(ins_phase) * rate / (2.0 * np.pi)
  freq_envelope_raw = np.insert(freq_envelope_raw, 0, freq_envelope_raw[0])

  freq_envelope_raw[freq_envelope_raw < 0] = np.nan
  upper_bound = 500

  logging.info('rm_outliers: kept frequency range: 0 %s', upper_bound)
  freq_envelope_raw[freq_envelope_raw > upper_bound] = np.nan
  freq_envelope_raw = pd.Series(freq_envelope_raw).interpolate().values
  freq_envelope_raw[np.isnan(freq_envelope_raw)] = 0

  sos = signal.butter(
      5, envelope_lowpass_cutoff / (rate / 2), btype='low', output='sos'
  )
  amp_envelope = signal.sosfiltfilt(sos, amp_envelope_raw)
  freq_envelope = signal.sosfiltfilt(sos, freq_envelope_raw)

  return amp_envelope, freq_envelope


def extract_vib_amp_freq(
    data: np.ndarray, rate: int, envelope_lowpass_cutoff: float = 100
) -> tuple[np.ndarray, np.ndarray]:
  """Extracts the vibration amplitude and frequency envelope from the data.

  Args:
    data: The vibration data.
    rate: The sampling rate of the data.
    envelope_lowpass_cutoff: The lowpass cutoff frequency for the envelope.

  Returns:
    A tuple of vibration amplitude and frequency envelopes.
  """
  data = copy.deepcopy(data)
  amp_envelope, freq_envelope = _calculate_freq_env(
      data, rate, envelope_lowpass_cutoff=envelope_lowpass_cutoff
  )

  chunks = common_utils.zero_out_low_amplitude_chunks(
      data, rate, amplitude_threshold_fraction=0.01, duration_threshold_ms=20
  )
  for _, (start, end) in enumerate(chunks):
    amp_envelope[start:end] = 0.0
    freq_envelope[start:end] = 0.0

  amp_envelope[-1] = 0.0
  freq_envelope[-1] = 0.0

  return amp_envelope, freq_envelope
