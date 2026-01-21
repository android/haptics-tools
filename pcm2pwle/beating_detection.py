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

"""Utility functions for detecting beating signals."""

import logging

import numpy as np
from scipy import fft
from scipy import signal

from pcm2pwle import common_utils
from pcm2pwle import control_point_extraction

sosfiltfilt = signal.sosfiltfilt
hilbert = signal.hilbert
find_peaks = signal.find_peaks
butter = signal.butter
rfft = fft.rfft
rfftfreq = fft.rfftfreq


def is_beating(
    data: np.ndarray,
    rate: int,
    peak_ratio_threshold: float = 2,
    freq_diff_threshold: float = 60,
    peak_energy_ratio_threshold: float = 0.1,
    energy_outside_peaks_ratio_threshold: float = 0.1,
) -> None | tuple[float, float]:
  """Checks if the given data is a beating signal.

  Args:
    data: The signal data to be checked.
    rate: The sampling rate of the data.
    peak_ratio_threshold: The threshold for the ratio of the FFT amplitudes at
      the two most prominent component frequencies.  The threshold for the ratio
      of the amplitude of the two peaks.
    freq_diff_threshold: The threshold for the frequency difference between the
      two most prominent component frequencies.
    peak_energy_ratio_threshold: The threshold for the ratio of the spectral
      energy at the two most prominent component frequencies to the total
      spectral energy.
    energy_outside_peaks_ratio_threshold: The threshold for the ratio of
      spectral energy outside the two most prominent component frequencies to
      the total spectral energy.

  Returns:
    None if the data is not a beating signal, otherwise returns a tuple of the
    two beat frequencies.
  """
  if data.size == 0:
    return None

  #### 1. FREQUENCY DOMAIN ANALYSIS ####
  xf = rfftfreq(len(data), 1 / rate)
  yf = rfft(data)
  yf = np.abs(yf) / np.max(np.abs(yf))

  sos = butter(5, rate / 10 / (rate / 2), btype='low', output='sos')
  yf = sosfiltfilt(sos, yf)

  peaks, properties = find_peaks(yf, prominence=0)

  # Not enough prominent peaks to create a beat
  if len(peaks) < 2:
    logging.warning(
        'Found %d peaks, not enough prominent peaks to create a beat',
        len(peaks),
    )
    return None

  prominences = properties['prominences']
  sorted_peak_indices = np.argsort(prominences)[::-1]
  peak1_idx, peak2_idx = peaks[sorted_peak_indices[:2]]

  freq1, freq2 = xf[peak1_idx], xf[peak2_idx]
  logging.info('freq1: %.2f Hz, freq2: %.2f Hz', freq1, freq2)
  fft_beat_freq = abs(freq1 - freq2)

  # Check if the frequency difference is within the plausible range for a beat
  logging.info('Frequency difference (%.2f Hz)', fft_beat_freq)
  if not (1 <= fft_beat_freq <= freq_diff_threshold):
    logging.warning(
        'Frequency difference (%.2f Hz) out of range [1 Hz, %d Hz]',
        fft_beat_freq,
        freq_diff_threshold,
    )
    return None

  # Check if the amplitude of the two peaks are close
  peak1_amp, peak2_amp = yf[peak1_idx], yf[peak2_idx]
  peak_ratio = peak1_amp / peak2_amp
  logging.info('peak1_amp: %.2f, peak2_amp: %.2f', peak1_amp, peak2_amp)
  logging.info('peak ratio: %.2f', peak_ratio)
  if peak_ratio > peak_ratio_threshold:
    logging.warning('peak ratio (%.2f) too large', peak_ratio)
    return None

  # Check peak energy is larger than a ratio of the spectrum energy
  peak_energy = yf[peak1_idx] ** 2 + yf[peak2_idx] ** 2
  spectrum_energy = np.sum(yf**2)
  peak_energy_ratio = peak_energy / spectrum_energy
  logging.info('peak energy ratio (%.2f)', peak_energy_ratio)
  if peak_energy_ratio < peak_energy_ratio_threshold:
    logging.warning('peak energy ratio (%.2f) too small', peak_energy_ratio)
    return None

  # Check if no energy outside of the two peaks
  spectrum_energy = np.sum(yf**2)
  freq_left = min(freq1, freq2) - 50
  freq_right = max(freq1, freq2) + 50
  energy_outside_peaks = np.sum(yf[(xf < freq_left) | (xf > freq_right)] ** 2)
  energy_outside_peaks_ratio = energy_outside_peaks / spectrum_energy
  logging.info('energy outside peaks ratio (%.2f)', energy_outside_peaks_ratio)
  if energy_outside_peaks_ratio > energy_outside_peaks_ratio_threshold:
    logging.warning(
        'energy outside peaks ratio (%.2f) too large',
        energy_outside_peaks_ratio,
    )
    return None

  #### 2. AMPLITUDE ENVELOPE ANALYSIS ####
  ## Check amplitude envelope valley point's freq are outliers
  analytic_signal = hilbert(data)
  amp_envelope = np.abs(analytic_signal)
  ins_phase = np.unwrap(np.angle(analytic_signal))
  freq_envelope = np.diff(ins_phase) / (2 * np.pi) * rate
  freq_envelope = np.insert(freq_envelope, 0, freq_envelope[0])

  chunks = common_utils.zero_out_low_amplitude_chunks(
      data,
      rate,
      amplitude_threshold_fraction=0.01,
      duration_threshold_ms=20,
  )
  for _, (start, end) in enumerate(chunks):
    amp_envelope[start:end] = 0.0
    freq_envelope[start:end] = 0.0

  logging.info(
      'envelope frequency: %.2f Hz, repeat distance: %.2f',
      fft_beat_freq,
      1 / fft_beat_freq * rate * 0.95,
  )
  valley_idxs, _ = find_peaks(
      -amp_envelope,
      distance=1 / fft_beat_freq * rate * 0.95,
      prominence=np.max(np.abs(amp_envelope)) * 0.1,
  )
  valley_freq = freq_envelope[valley_idxs]
  mean_valley_freq = np.mean(np.abs(valley_freq))
  freq_q3 = np.quantile(np.abs(freq_envelope), 0.75)
  freq_q1 = np.quantile(np.abs(freq_envelope), 0.25)
  freq_iqr = freq_q3 - freq_q1
  outlier_freq = freq_q3 + 1.5 * freq_iqr
  logging.info(
      'mean valley frequency: %.2f Hz, outlier frequency: %.2f Hz',
      mean_valley_freq,
      outlier_freq,
  )
  avg_freq = (freq1 + freq2) / 2
  outlier_freq_low = avg_freq - 10
  outlier_freq_high = min(avg_freq * 2, outlier_freq)
  logging.info(
      'mean valley frequency: %.2f Hz, outlier frequency: %.2f Hz %.2f Hz',
      mean_valley_freq,
      outlier_freq_low,
      outlier_freq_high,
  )
  if (
      outlier_freq_low < mean_valley_freq < outlier_freq_high
      or min(abs(valley_freq)) == 0
  ):
    logging.warning(
        'mean valley frequency (%.2f Hz) is not outlier',
        mean_valley_freq,
    )
    return None

  return (freq1, freq2)


def extract_beating_control_points(
    amp_envelope: np.ndarray,
    freq_envelope: np.ndarray,
    beating_freqs: tuple[float, float],
    rate: int,
    error_threshold: float,
    jnd_multiple: float,
) -> list[common_utils.ControlPoint]:
  """Extracts the control points from the amplitude envelope and frequency envelope.

  Args:
    amp_envelope: Amplitude envelope of the signal.
    freq_envelope: Frequency envelope of the signal.
    beating_freqs: The two component frequencies of the beating signal.
    rate: Sampling rate of the signal.
    error_threshold: The error threshold for Ramer-Douglas-Peucker algorithm.
    jnd_multiple: The JND multiple for the control points.

  Returns:
    A list of ControlPoint.
  """
  carrier_freq = (beating_freqs[0] + beating_freqs[1]) / 2
  beating_freq = np.abs(beating_freqs[0] - beating_freqs[1])

  amp_fitted_downsampled, freq_fitted_downsampled = (
      common_utils.preprocess_envelopes(amp_envelope, freq_envelope, rate)
  )

  all_amp_points = control_point_extraction.rdp(
      amp_fitted_downsampled,
      epsilon=error_threshold,
      point_type=common_utils.PointType.AMPLITUDE,
  )

  # JND value default to 1.5dB * multiplier for vibration amplitude and
  # frequency.
  amp_points = control_point_extraction.rdp_with_min_distance(
      all_amp_points,
      min_duration_ms=common_utils.MIN_DURATION,
      perceiption_jnd=1.5 * jnd_multiple,
  )

  control_points = []
  for point in amp_points:
    control_points.append(
        common_utils.ControlPoint(
            time=point.time,
            amplitude=point.amplitude,
            frequency=carrier_freq,
            time_shift=point.time_shift,
        )
    )

  control_points = common_utils.zero_amplitude_at_zero_frequency(
      control_points, freq_fitted_downsampled
  )
  control_points = common_utils.set_fist_last_point_amp_to_zero(control_points)
  logging.info('Number of control points: %d', len(control_points))

  common_utils.reject_invalid_waveform(
      control_points, time_shift_threshold=100, mean_freq_threshold=25
  )
  common_utils.reject_invalid_beating_waveform(
      beating_freq, common_utils.MIN_DURATION
  )

  return control_points
