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

"""Common utility functions."""

import dataclasses
import enum
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
from xml.dom import minidom
import xml.etree.ElementTree as ET

import numpy as np
from scipy import signal
from scipy.io import wavfile
import soundfile as sf


Enum = enum.Enum
decimate = signal.decimate
medfilt = signal.medfilt

MIN_DURATION = 20
JND_MULTIPLE = MIN_DURATION / 10
# JND value default to 1dB * multiplier for vibration intensity and
# 1.5dB * multiplier for vibration amplitude and frequency
AMPLITUDE_FREQUENCY_JND = 1.5 * JND_MULTIPLE
INTENSITY_JND = 1.0 * JND_MULTIPLE
AMP_LOWER_LIMIT = 0
AMP_UPPER_LIMIT = 1

# Frequency profile for basic PWLE mapping.
# (freq_lower_limit, res_freq, freq_upper_limit)
PWLE_FREQ_PROFILE = (50.0, 136.0, 174.0)


@dataclasses.dataclass
class AdvancedPWLEPoint:
  """Class to encapsulate attributes of advanced PWLE points.

  Attributes:
    amplitude: Amplitude value in the range of [0, 1] represents the achievable
      strength at given frequency, as determined by the device FOAM.
    frequency: Frequency is specified directly in Hertz.
    duration: Duration is the time taken to transition from the last PWLE point
      to the new one, in milliseconds.
  """
  amplitude: float
  frequency: float
  duration: int


@dataclasses.dataclass
class BasicPWLEPoint:
  """Class to encapsulate attributes of basic PWLE points.

  Attributes:
    intensity: Intensity value in the range of [0, 1] represents the perceived
      strength of the vibration.
    sharpness: Sharpness value in the range of [0, 1] represents the crispness
      of the vibration.
    duration: Duration is the time taken to transition from the last PWLE point
      to the new one, in milliseconds.
  """
  intensity: float
  sharpness: float
  duration: int


class PointType(Enum):
  """Point type for control point."""
  # Frequency only.
  FREQUENCY = 1
  # Amplitude only.
  AMPLITUDE = 2
  # Combined frequency and amplitude.
  COMBINED = 3


@dataclasses.dataclass
class ControlPoint:
  """Class to encapsulate attributes for control points.

  Control point is a middle step referring to the points extracted from the RDP
  algorithm and subsequent post-processing. It will be converted to either
  BasicPWLEPoint or AdvancedPWLEPoint
  for PWLE fitting.

  Attributes:
    amplitude: The amplitude of the control point, in [0, 1]. Optional.
    frequency: The frequency of the control point, in Hz. Optional.
    time: The timestamp of the control point, in milliseconds.
    time_shift: The time shift of the control point from its initially
      extraction by RDP algorithm to its final version after all post-processing
      and right before converting to PWLE points.
  """
  amplitude: Optional[float]
  frequency: Optional[float]
  time: float
  time_shift: float = 0

  @classmethod
  def from_data_point(
      cls, data_point: np.ndarray, point_type: PointType
  ) -> 'ControlPoint':
    """Constructs a ControlPoint from a data point."""
    if point_type == PointType.FREQUENCY:
      return cls(
          frequency=data_point[1], amplitude=None, time=data_point[0]
      )
    elif point_type == PointType.AMPLITUDE:
      return cls(
          frequency=None, amplitude=data_point[1], time=data_point[0]
      )
    elif point_type == PointType.COMBINED:
      return cls(
          frequency=data_point[1], amplitude=data_point[2], time=data_point[0]
      )
    else:
      raise ValueError(
          f'Unknown point type: {point_type}, must be FREQUENCY, AMPLITUDE, or'
          ' COMBINED'
      )


def load_pcm_file(file_path: str) -> Tuple[np.ndarray, int]:
  """Loads PCM data and sample rate from a wav or ogg file.

  Args:
    file_path: Path to the raw PCM file.

  Returns:
    A tuple of (data, sample_rate).

  Raises:
    ValueError: If the file format is unsupported or the OGG channel count
      is insufficient.
  """
  if file_path.endswith('.wav'):
    with open(file_path, 'rb') as f:
      rate, data = wavfile.read(f)
      # Take the first channel if stereo
      if data.ndim > 1:
        data = data[:, 0]
      return data, rate
  elif file_path.endswith('.ogg'):
    with open(file_path, 'rb') as f:
      data, rate = sf.read(f)
      # Vibration data stored in the second channel for internal ogg files.
      if data.ndim != 2 or data.shape[1] < 2:
        raise ValueError(
            'OGG file must have at least 2 channels for vibration data.'
        )
      data = data[:, 1]
      return data, rate
  else:
    raise ValueError(
        f'Unsupported file extension in {file_path}. Only .wav and .ogg'
        ' files are supported.'
    )


def parse_haptics_xml(
    xml_path: str,
) -> Tuple[List[List[Dict[str, Any]]], str, List[Dict[str, Any]]]:
  """Parses a Haptics XML file into a list of envelopes and presets.

  Args:
    xml_path: Path to the XML file.

  Returns:
    A tuple of (envelopes, pwle_type, presets).
    - envelopes is a list of lists, where each inner list represents the
      absolute control points of a single, disjoint envelope.
    - presets is a list of dictionaries representing short preset effects.
  """
  tree = ET.parse(xml_path)
  root = tree.getroot()

  envelopes = []
  presets = []
  pwle_type = None

  for event in root.iter():
    if event.tag.endswith('event'):
      start_time = int(event.get('startTimeMillis', 0))
      for child in event:
        if child.tag.endswith('basicEnvelope'):
          pwle_type = 'basic_pwle'
          initial_sharpness = float(child.get('initialSharpness', 0))

          envelope_points = [{
              'time': start_time,
              'intensity': 0.0,
              'sharpness': initial_sharpness,
          }]

          curr_time = start_time
          for cp in child:
            if cp.tag.endswith('controlPoint'):
              duration = int(cp.get('durationMillis', 0))
              curr_time += duration
              envelope_points.append({
                  'time': curr_time,
                  'intensity': float(cp.get('intensity', 0)),
                  'sharpness': float(cp.get('sharpness', 0)),
              })
          envelopes.append(envelope_points)

        elif child.tag.endswith('advancedEnvelope'):
          pwle_type = 'advanced_pwle'
          initial_freq = float(child.get('initialFrequency', 0))

          envelope_points = [{
              'time': start_time,
              'amplitude': 0.0,
              'frequency': initial_freq,
          }]

          curr_time = start_time
          for cp in child:
            if cp.tag.endswith('controlPoint'):
              duration = int(cp.get('durationMillis', 0))
              curr_time += duration
              envelope_points.append({
                  'time': curr_time,
                  'amplitude': float(cp.get('amplitude', 0)),
                  'frequency': float(cp.get('frequencyHz', 0)),
              })
          envelopes.append(envelope_points)

        elif child.tag.endswith('preset'):
          presets.append({
              'time': start_time,
              'presetEnum': child.get('presetEnum'),
              'intensity': float(child.get('intensity', 1.0)),
          })

  if pwle_type is None and not presets:
    raise ValueError(
        'Invalid XML: missing basicEnvelope, advancedEnvelope, or preset.'
    )

  # Sort envelopes by the start time of their first point to ensure they
  # are sequential.
  envelopes.sort(key=lambda x: x[0]['time'])

  return envelopes, pwle_type, presets


def generate_haptics_xml(
    points: Sequence[Any],
    pwle_type: str,
    output_path: str,
    xml_version: str,
    preset_insert_points: list[tuple[float, float]] | None = None,
) -> str:
  """Generates a string structured as the required Haptics XML format.

  Args:
    points: A list of PWLE point objects representing the effect elements.
    pwle_type: The type string for the haptic object.
    output_path: the XML string will be written to this file path.
    xml_version: The version string for the XML format.
    preset_insert_points: optional list of preset insert points.

  Returns:
    A generated XML string.
  """
  root = ET.Element('hapticPattern', version=xml_version)
  effect = ET.SubElement(root, 'hapticEffect')

  # Combine PWLE points and preset insert points, sorted by time
  events = []
  curr_time = 0
  for p in points:
    # First point has duration 0, skip for timing calculation
    if hasattr(p, 'duration'):
      curr_time += p.duration
    events.append({'time': curr_time, 'type': 'pwle', 'data': p})

  if preset_insert_points:
    for start_time, intensity in preset_insert_points:
      events.append({
          'time': start_time,
          'type': 'preset',
          'data': {'intensity': intensity},
      })

  # Sort events by time
  events.sort(key=lambda x: (x['time'], 0 if x['type'] == 'preset' else 1))

  # Group PWLE points into pieces separated by presets
  current_pwle_piece = []
  last_pwle_time = 0

  for event_data in events:
    if event_data['type'] == 'preset':
      # If we have a pending PWLE piece, add it as an event
      if current_pwle_piece:
        _add_pwle_event(
            effect, current_pwle_piece, pwle_type, last_pwle_time
        )
        current_pwle_piece = []

      # Add the preset event
      prim_event = ET.SubElement(
          effect, 'event', startTimeMillis=str(int(event_data['time']))
      )
      ET.SubElement(
          prim_event,
          'preset',
          # Use CLICK for detected pulses.
          presetEnum='CLICK',
          intensity=str(float(event_data['data']['intensity'])),
      )
    else:
      p = event_data['data']
      if not current_pwle_piece:
        last_pwle_time = event_data['time']
        # If it's the start of a new piece, we need to handle the first point
        # differently because it has no duration. We'll adjust subsequent
        # points' durations to be relative to this piece's start.
        if hasattr(p, 'duration'):
          # Create a starting point with 0 duration and same values as p
          if pwle_type == 'advanced_pwle':
            start_p = AdvancedPWLEPoint(
                amplitude=p.amplitude,
                frequency=p.frequency,
                duration=0,
            )
          else:
            start_p = BasicPWLEPoint(
                intensity=p.intensity,
                sharpness=p.sharpness,
                duration=0,
            )
          current_pwle_piece.append(start_p)
        else:
          # This is the very first point of the original points list
          current_pwle_piece.append(p)
      else:
        # Add point with its original duration (which is relative to prev point)
        current_pwle_piece.append(p)

  # Add any remaining PWLE piece
  if current_pwle_piece:
    _add_pwle_event(effect, current_pwle_piece, pwle_type, last_pwle_time)

  xml_string = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")

  with open(output_path, 'w') as f:
    f.write(xml_string)
    print(f'Successfully wrote Haptics XML to {output_path}')

  return xml_string


def _add_pwle_event(
    effect: ET.Element,
    points: list[Any],
    pwle_type: str,
    start_time: float,
) -> None:
  """Adds a PWLE event to the effect element."""
  # Only add if there are more than just the initial point
  if len(points) <= 1:
    return

  event = ET.SubElement(effect, 'event', startTimeMillis=str(int(start_time)))

  if pwle_type == 'advanced_pwle':
    envelope = ET.SubElement(event, 'advancedEnvelope')
    envelope.set('initialFrequency', str(float(points[0].frequency)))
    for p in points[1:]:
      ET.SubElement(
          envelope,
          'controlPoint',
          amplitude=str(float(p.amplitude)),
          frequencyHz=str(float(p.frequency)),
          durationMillis=str(int(p.duration)),
      )
  elif pwle_type == 'basic_pwle':
    envelope = ET.SubElement(event, 'basicEnvelope')
    envelope.set('initialSharpness', str(float(points[0].sharpness)))
    for p in points[1:]:
      ET.SubElement(
          envelope,
          'controlPoint',
          intensity=str(float(p.intensity)),
          sharpness=str(float(p.sharpness)),
          durationMillis=str(int(p.duration)),
      )


def perceived_intensity(amp: float, freq: float) -> float:
  """Perceived intensity given the amplitude and frequency.

  See more detail at "Hwang, I., Seo, J., Kim, M., & Choi, S. (2013).
  Vibrotactile perceived intensity for mobile devices as a function of
  direction, amplitude, and frequency. IEEE Transactions on Haptics".

  Args:
    amp: Amplitude value in the range of [0, 1].
    freq: Frequency in Hz.

  Returns:
    Perceived intensity.
  """
  if freq < 50:
    freq = 50

  f_log = math.log10(freq)
  k = 267 - 373 * f_log + 177 * np.power(f_log, 2) - 27.8 * np.power(f_log, 3)
  e = -2.28 + 8.04 * f_log -5.48 * np.power(f_log, 2) + 1.1 * np.power(f_log, 3)

  p_int = k * np.power(amp, e)

  return p_int


def zero_out_low_amplitude_chunks(
    data: np.ndarray,
    rate: int,
    amplitude_threshold_fraction: float = 0.05,
    duration_threshold_ms: int = 20,
    amp_max: Optional[float] = None,
) -> list[tuple[int, int]]:
  """Finds consecutive near-zero chunks in a signal that last longer than min_duration.

  Args:
    data: Input 1D signal.
    rate: Sampling rate in Hz.
    amplitude_threshold_fraction: Values with abs() below this are considered
      near zero.
    duration_threshold_ms: Minimum chunk duration in milliseconds.
    amp_max: If not None, use this as the amplitude max value. Otherwise, use
      the max absolute value of the data.

  Returns:
    List of (start_idx, end_idx) tuples (in sample indices) for each chunk
    found.
  """
  if amp_max is None:
    amp_max = np.max(np.abs(data))

  sig = np.abs(np.asarray(data)) < amplitude_threshold_fraction * amp_max
  min_length = int(duration_threshold_ms / 1000 * rate)

  chunks = []
  start = None

  for i, val in enumerate(sig):
    if val and start is None:
      start = i
    elif not val and start is not None:
      if i - start >= min_length:
        chunks.append((start, i))
      start = None

  # Handle case where signal ends in a near-zero chunk
  if start is not None and len(sig) - start >= min_length:
    chunks.append((start, len(sig)))

  return chunks


def _downsample_signal(
    data: np.ndarray, original_rate: int, downsampling_factor: int
) -> np.ndarray:
  """Downsamples the signal."""
  signal_duration = len(data) / original_rate * 1000

  downsampled_signal = decimate(data, downsampling_factor)

  downsampled_signal[downsampled_signal < 0] = 0.0

  time_vector = np.linspace(
      0, signal_duration, len(downsampled_signal), endpoint=False
  )

  return np.vstack((time_vector, downsampled_signal)).T


def preprocess_envelopes(
    amp_envelope: np.ndarray, freq_envelope: np.ndarray, rate: int
) -> tuple[np.ndarray, np.ndarray]:
  """Preprocess the amplitude and frequency envelopes.

  Args:
    amp_envelope: Amplitude envelope of the signal.
    freq_envelope: Instantaneous frequency envelope of the signal.
    rate: Sampling rate of the signal.

  Returns:
    A tuple of preprocessed amplitude and frequency envelopes.
  """
  time = [i / rate * 1000 for i in range(len(amp_envelope))]

  # Filter amp & freq curve
  median_filter_k = int(rate * 0.01 // 2 * 2 + 1)
  amp_fitted = medfilt(amp_envelope, kernel_size=median_filter_k)
  amp_fitted[0] = 0.
  amp_fitted[-1] = 0.
  amp_fitted = np.array(list(zip(time, amp_fitted)))

  freq_fitted = medfilt(freq_envelope, kernel_size=median_filter_k)
  freq_fitted = np.array(list(zip(time, freq_fitted)))

  # amp & freq curve downsample
  ds_k = int(rate / 1000)
  amp_fitted_downsampled = _downsample_signal(amp_fitted[:, 1], rate, ds_k)
  freq_fitted_downsampled = _downsample_signal(freq_fitted[:, 1], rate, ds_k)

  # set value to 0 for long silence period
  chunks = zero_out_low_amplitude_chunks(amp_envelope, rate,
                                         amplitude_threshold_fraction=0.01,
                                         duration_threshold_ms=10)
  for _, (start, end) in enumerate(chunks):
    start_time = start / rate * 1000
    end_time = end / rate * 1000
    amp_fitted_downsampled[
        (amp_fitted_downsampled[:, 0] >= start_time)
        & (amp_fitted_downsampled[:, 0] <= end_time),
        1,
    ] = 0.0
    freq_fitted_downsampled[
        (freq_fitted_downsampled[:, 0] >= start_time)
        & (freq_fitted_downsampled[:, 0] <= end_time),
        1,
    ] = 0.0

  return amp_fitted_downsampled, freq_fitted_downsampled


def zero_amplitude_at_zero_frequency(
    control_points: list[ControlPoint], envelope: np.ndarray
) -> list[ControlPoint]:
  """Zero out the amplitude at zero frequency.

  Args:
    control_points: A list of control points.
    envelope: The envelope of the signal.

  Returns:
    A list of control points with zero amplitude at zero frequency.
  """
  new_control_points = []
  for p in control_points:
    if p.frequency == 0:
      p.amplitude = 0.
    if p.time > envelope[-1, 0] + 20:
      continue
    new_control_points.append(p)
  return new_control_points


def set_fist_last_point_amp_to_zero(
    control_points: list[ControlPoint], amp_to_keep_ratio: float = 0.05
) -> list[ControlPoint]:
  """Set the first and last point amplitude to zero.

  Args:
    control_points: A list of control points.
    amp_to_keep_ratio: The ratio of the amplitude to keep.

  Returns:
    A list of control points with first and last point amplitude set to zero.
  """

  amp_peak = max(point.amplitude for point in control_points)

  if control_points[0].amplitude >= amp_to_keep_ratio * amp_peak:
    first_point_to_add = ControlPoint(
        time=0, frequency=control_points[0].frequency, amplitude=0.0
    )
    for p in control_points:
      p.time += MIN_DURATION
    control_points = [first_point_to_add] + control_points
  else:
    control_points[0].amplitude = 0.

  if control_points[-1].amplitude >= amp_to_keep_ratio * amp_peak:
    last_point_to_add = ControlPoint(
        time=control_points[-1].time + MIN_DURATION,
        frequency=control_points[-1].frequency,
        amplitude=0.0,
    )
    control_points = control_points + [last_point_to_add]
  else:
    control_points[-1].amplitude = 0.

  return control_points


def reject_invalid_waveform(
    control_points: list[ControlPoint],
    time_shift_threshold: float,
    mean_freq_threshold: float,
) -> bool:
  """Reject invalid waveform.

  Args:
    control_points: A list of control points.
    time_shift_threshold: The threshold for the time shift.
    mean_freq_threshold: The threshold for the mean frequency.

  Returns:
    True if the waveform is invalid, False otherwise.
  """
  time_shift_list = [p.time_shift for p in control_points if p.amplitude != 0]
  if time_shift_list and np.max(time_shift_list) > time_shift_threshold:
    print(
        f'WARNING: max_time_shift {np.max(time_shift_list)} > '
        f' {time_shift_threshold}'
    )
    return True

  freq_list = [p.frequency for p in control_points if p.frequency != 0]
  if freq_list and np.mean(freq_list) < mean_freq_threshold:
    print(
        f'WARNING: mean_freq {np.mean(freq_list)} < {mean_freq_threshold}')
    return True

  return False


def reject_invalid_beating_waveform(
    beating_freq: float) -> bool:
  """Reject invalid beating waveform.

  Args:
    beating_freq: The frequency of the beating.

  Returns:
    True if the waveform is invalid, False otherwise.
  """
  rejection_freq = 1000 / (2 * MIN_DURATION)
  if beating_freq > rejection_freq:
    print(
        f'WARNING: beating_freq {beating_freq} > {rejection_freq}'
    )
    return True
  return False


def generate_advanced_pwle(
    control_points: Sequence[ControlPoint],
) -> Sequence[AdvancedPWLEPoint]:
  """Generates advanced PWLE representation given a sequence of control points.

  Args:
    control_points: A list of control points.

  Returns:
    A list of advanced PWLE points.
  """
  max_amp = max([p.amplitude for p in control_points])
  max_amp = min(max_amp, AMP_UPPER_LIMIT)
  if max_amp == 0:
    max_amp = AMP_UPPER_LIMIT

  pwle_points = []
  for i in range(len(control_points)):
    p_amp = control_points[i].amplitude
    p_freq = control_points[i].frequency
    p_time = control_points[i].time

    ### Amplitude
    # Clip amplitude to [AMP_LOWER_LIMIT, AMP_UPPER_LIMIT] and then normalize
    # the amplitudes.
    if p_amp < AMP_LOWER_LIMIT:
      p_amp = AMP_LOWER_LIMIT
    if p_amp > AMP_UPPER_LIMIT:
      p_amp = AMP_UPPER_LIMIT
    p_amp = p_amp / max_amp

    ### Duration
    p_duration = 0 if i == 0 else p_time - control_points[i - 1].time

    pwle_points.append(
        AdvancedPWLEPoint(
            amplitude=p_amp,
            frequency=p_freq,
            duration=round(p_duration),
        )
    )

  return pwle_points


def sharpness_to_freq(
    sharpness: float,
    freq_profile: tuple[float, float, float] = PWLE_FREQ_PROFILE,
) -> float:
  """Maps sharpness back to frequency.

  Args:
    sharpness: Sharpness value in [0, 1].
    freq_profile: A tuple of (freq_lower_limit, res_freq, freq_upper_limit).

  Returns:
    Mapped frequency in Hz.
  """
  freq_lower_limit, res_freq, freq_upper_limit = freq_profile
  if sharpness <= 0.7:
    return (
        sharpness / 0.7 * (res_freq - freq_lower_limit) + freq_lower_limit
    )
  else:
    return (
        (sharpness - 0.7) / 0.3 * (freq_upper_limit - res_freq) + res_freq
    )


def freq_to_sharpness(
    freq: float,
    freq_profile: tuple[float, float, float] = PWLE_FREQ_PROFILE,
) -> float:
  """Maps frequency to sharpness.

  Args:
    freq: Frequency value in Hz.
    freq_profile: A tuple of (freq_lower_limit, res_freq, freq_upper_limit).

  Returns:
    Mapped sharpness in [0, 1].
  """
  freq_lower_limit, res_freq, freq_upper_limit = freq_profile

  if freq < freq_lower_limit:
    freq = freq_lower_limit
  if freq > freq_upper_limit:
    freq = freq_upper_limit

  if freq <= res_freq:
    return (freq - freq_lower_limit) / (res_freq - freq_lower_limit) * 0.7
  else:
    return (freq - res_freq) / (freq_upper_limit - res_freq) * 0.3 + 0.7


def generate_basic_pwle(
    control_points: Sequence[ControlPoint],
    freq_profile: tuple[float, float, float] = PWLE_FREQ_PROFILE,
) -> Sequence[BasicPWLEPoint]:
  """Generates basic PWLE representation given a sequence of control points.

  Args:
    control_points: A list of control points.
    freq_profile: A tuple of (freq_lower_limit, res_freq, freq_upper_limit).

  Returns:
    A list of basic PWLE points.
  """
  max_amp = max([p.amplitude for p in control_points])
  max_amp = min(max_amp, AMP_UPPER_LIMIT)
  if max_amp == 0:
    max_amp = AMP_UPPER_LIMIT

  pwle_points = []
  for i in range(len(control_points)):
    p_amp = control_points[i].amplitude
    p_freq = control_points[i].frequency
    p_time = control_points[i].time

    ### Amplitude
    # Clip amplitude to [AMP_LOWER_LIMIT, AMP_UPPER_LIMIT] and then normalize
    # the amplitudes.
    if p_amp < AMP_LOWER_LIMIT:
      p_amp = AMP_LOWER_LIMIT
    if p_amp > AMP_UPPER_LIMIT:
      p_amp = AMP_UPPER_LIMIT
    p_amp = p_amp / max_amp

    ### Frequency
    # Clip frequency to [freq_lower_limit, freq_upper_limit] and then do a
    # linear extrapolation with the resonant frequency being mapped to 0.7.
    p_sharpness = freq_to_sharpness(p_freq, freq_profile=freq_profile)

    ### Duration
    p_duration = 0 if i == 0 else p_time - control_points[i - 1].time

    pwle_points.append(
        BasicPWLEPoint(
            intensity=p_amp,
            sharpness=p_sharpness,
            duration=round(p_duration),
        )
    )

  return pwle_points
