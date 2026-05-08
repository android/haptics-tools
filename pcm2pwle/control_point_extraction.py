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

"""Control point extraction."""

import copy
import logging
import math

import numpy as np
from scipy import interpolate

from pcm2pwle import common_utils


interp1d = interpolate.interp1d


def rdp(
    data: np.ndarray, epsilon: float, point_type: common_utils.PointType
) -> list[common_utils.ControlPoint]:
  """Applies the Ramer-Douglas-Peucker algorithm to simplify the signal (data) into piecewise linear curve.

  Args:
    data: A NumPy array representing the signal.
    epsilon: The detection tolerance. Points further than this distance from the
      line segment will be kept. Larger epsilon results in fewer key points.
    point_type: The type of point to be extracted.

  Returns:
    A 2D NumPy array of the (x, y) coordinates of the simplified piecewise
    linear curve.
  """
  if len(data) <= 2:
    return np.vstack((np.arange(len(data)), data)).T

  if len(data[0]) < 2:
    # use index as x if data is 1d, and y is the data value
    points_raw = np.vstack((np.arange(len(data)), data)).T
  else:
    points_raw = data

  # Start with the first and last points
  indices = [0, len(points_raw) - 1]
  points = copy.deepcopy(points_raw)
  data_max = np.max(data[:, 1])
  if data_max:
    points[:, 1] = points[:, 1] / data_max
  points[:, 0] = points[:, 0] / 1000

  def _rdp_recursive(start_index, end_index):
    max_dist = 0.0
    index_of_max_dist = 0

    p1 = points[start_index]
    p2 = points[end_index]

    # Calculate the distance from each intermediate point to the line segment
    # defined by p1 and p2.
    # Line equation: (x - x1)(y2 - y1) - (y - y1)(x2 - x1) = 0
    # Distance from (x0, y0) to Ax + By + C = 0 is
    #   |Ax0 + By0 + C| / sqrt(A^2 + B^2)
    # where A = (y2 - y1), B = -(x2 - x1), C = -x1(y2 - y1) + y1(x2 - x1)

    # Vector from p1 to p2
    line_vec = p2 - p1
    line_len_sq = np.dot(line_vec, line_vec)

    if line_len_sq == 0:  # Points are coincident, no line
      for i in range(start_index + 1, end_index):
        dist = np.linalg.norm(points[i] - p1)  # Distance to p1
        if dist > max_dist:
          max_dist = dist
          index_of_max_dist = i
    else:
      for i in range(start_index + 1, end_index):
        point_vec = points[i] - p1

        # Projection of point_vec onto line_vec
        t = np.dot(point_vec, line_vec) / line_len_sq

        if t < 0:
          closest_point = p1
        elif t > 1:
          closest_point = p2
        else:
          closest_point = p1 + t * line_vec

        dist = np.linalg.norm(points[i] - closest_point)

        if dist > max_dist:
          max_dist = dist
          index_of_max_dist = i

    if max_dist > epsilon:
      _rdp_recursive(start_index, index_of_max_dist)
      indices.append(index_of_max_dist)
      _rdp_recursive(index_of_max_dist, end_index)

  _rdp_recursive(0, len(points) - 1)

  indices = sorted(list(set(indices)))
  rdp_points = [
      common_utils.ControlPoint.from_data_point(data_point, point_type)
      for data_point in points_raw[indices]
  ]

  return rdp_points


def _is_within_jnd_db(a1: float, a2: float, jnd_db: float, c: float) -> bool:
  """Checks if the two amplitudes are within the JND in dB."""
  a1 = max(a1, 0.01)
  a2 = max(a2, 0.01)
  db = c * abs(math.log10(a2 / a1))
  return db <= jnd_db


def _remove_control_points(
    current_point_rdp: common_utils.ControlPoint,
    last_kept_point: common_utils.ControlPoint,
    next_rdp_point: common_utils.ControlPoint,
    pwle_type: str,
) -> bool:
  """Removes control points if they are perceived to be the same as its neighbor points."""
  if pwle_type == "advanced_pwle":

    if current_point_rdp.amplitude is not None:
      # data has only amplitude, no frequency
      if current_point_rdp.frequency is None:
        cur_amp = current_point_rdp.amplitude
        last_amp = last_kept_point.amplitude
        next_amp = next_rdp_point.amplitude
        # if perceived similar to both previous and next points, then remove
        if _is_within_jnd_db(
            cur_amp, last_amp, jnd_db=common_utils.AMPLITUDE_FREQUENCY_JND, c=20
        ) and _is_within_jnd_db(
            cur_amp, next_amp, jnd_db=common_utils.AMPLITUDE_FREQUENCY_JND, c=20
        ):
          return True
        # if perceived similar to previous point and also really close to the
        # previous point, then remove
        if (
            _is_within_jnd_db(
                cur_amp,
                last_amp,
                jnd_db=common_utils.AMPLITUDE_FREQUENCY_JND,
                c=20,
            )
            and current_point_rdp.time - last_kept_point.time
            <= common_utils.MIN_DURATION / 2
        ):
          return True
        # else keep
        return False

      # data has both amplitude and frequency
      else:
        cur_p_int = common_utils.perceived_intensity(
            current_point_rdp.amplitude, current_point_rdp.frequency
        )
        last_p_int = common_utils.perceived_intensity(
            last_kept_point.amplitude, last_kept_point.frequency
        )
        next_p_int = common_utils.perceived_intensity(
            next_rdp_point.amplitude, next_rdp_point.frequency
        )
        # if perceived similar to both previous and next points, then remove
        if _is_within_jnd_db(
            cur_p_int, last_p_int, jnd_db=common_utils.INTENSITY_JND, c=10
        ) and _is_within_jnd_db(
            cur_p_int, next_p_int, jnd_db=common_utils.INTENSITY_JND, c=10
        ):
          return True
        # if perceived similar to previous point and also really close to the
        # previous point, then remove
        if (
            _is_within_jnd_db(
                cur_p_int, last_p_int, jnd_db=common_utils.INTENSITY_JND, c=10
            )
            and current_point_rdp.time - last_kept_point.time
            <= common_utils.MIN_DURATION / 2
        ):
          return True
        # else keep
        return False

    else:
      raise ValueError("Amplitude is required for input rdp_points.")

  elif pwle_type == "basic_pwle":

    if current_point_rdp.amplitude is not None:
      cur_amp = current_point_rdp.amplitude
      last_amp = last_kept_point.amplitude
      next_amp = next_rdp_point.amplitude

      # no matter rdp point has frequency or not, directly use amplitude as it
      # is intensity for basicPWLE if perceived similar to both previous and
      # next points, then remove
      if _is_within_jnd_db(
          cur_amp, last_amp, jnd_db=common_utils.INTENSITY_JND, c=10
      ) and _is_within_jnd_db(
          cur_amp, next_amp, jnd_db=common_utils.INTENSITY_JND, c=10
      ):
        return True
      # if perceived similar to previous point and also really close to the
      # previous point, then remove
      if (
          _is_within_jnd_db(
              cur_amp, last_amp, jnd_db=common_utils.INTENSITY_JND, c=10
          )
          and current_point_rdp.time - last_kept_point.time
          <= common_utils.MIN_DURATION / 2
      ):
        return True
      # else keep
      return False

    else:
      raise ValueError("Amplitude is required for input rdp_points.")

  else:
    raise ValueError("Invalid PWLE type: ", pwle_type)


def rdp_with_min_distance(
    rdp_points: list[common_utils.ControlPoint],
    pwle_type: str):
  """Simplify the extracted Ramer-Douglas-Peucker points.

  1. minimum duration between two adjucent points is MIN_DURATION (following
     PWLE rule)
  2. Remove redundant points if they perceived to be the indifferentiable

  Args:
    rdp_points: A list of ControlPoint.
    pwle_type: The type of PWLE. Either 'advanced_pwle' or 'basic_pwle'.

  Returns:
    A list of ControlPoint.
  """

  if common_utils.MIN_DURATION <= 0:
    return rdp_points

  final_rdp_points = [rdp_points[0]]
  for i in range(1, len(rdp_points)):
    current_point_rdp = rdp_points[i]
    last_kept_point = final_rdp_points[-1]

    # Check if the current RDP point is too close to the last kept point.
    duration_cur_to_last_kept = current_point_rdp.time - last_kept_point.time
    if duration_cur_to_last_kept < common_utils.MIN_DURATION - 1e-6:

      if i + 1 < len(rdp_points):
        next_rdp_point = rdp_points[i+1]
        remove_point = _remove_control_points(
            current_point_rdp,
            last_kept_point,
            next_rdp_point,
            pwle_type)

        if not remove_point:
          new_x_current = last_kept_point.time + common_utils.MIN_DURATION
          modified_point = copy.deepcopy(current_point_rdp)
          modified_point.time = new_x_current

          # track the time shift of the point
          time_shift = new_x_current - current_point_rdp.time
          modified_point.time_shift += time_shift

          final_rdp_points.append(modified_point)
        else:
          pass

    else:
      # The point is far enough from the last kept point. Keep it as is.
      final_rdp_points.append(current_point_rdp)

  ## Ensure the very last point of the original RDP points is always included
  if not final_rdp_points or not np.array_equal(
      final_rdp_points[-1], rdp_points[-1]
  ):
    final_rdp_points.append(rdp_points[-1])
    if (
        final_rdp_points[-1].time - final_rdp_points[-2].time
        < common_utils.MIN_DURATION
    ):
      final_rdp_points[-1].time = (
          final_rdp_points[-2].time + common_utils.MIN_DURATION
      )

  return final_rdp_points


def _combine_amp_freq_points_selective(
    amp_points: list[common_utils.ControlPoint],
    amp_fitted: np.ndarray,
    freq_points: list[common_utils.ControlPoint],
    freq_fitted: np.ndarray,
    pwle_type: str,
) -> list[common_utils.ControlPoint]:
  """Combines amplitude and frequency points.

  Keep all amplitude points and selectively adding frequency points based on
  frequency change and temporal proximity to amplitude points.

  Args:
    amp_points: A list of amplitude points.
    amp_fitted: The fitted amplitude envelope.
    freq_points: A list of frequency points.
    freq_fitted: The fitted frequency envelope.
    pwle_type: The type of PWLE. Either 'advanced_pwle' or 'basic_pwle'.

  Returns:
    A list of combined points.
  """
  amp_interp = interp1d(
      amp_fitted[:, 0],
      amp_fitted[:, 1],
      kind="linear",
      fill_value="extrapolate",
      bounds_error=False,
  )
  freq_interp = interp1d(
      freq_fitted[:, 0],
      freq_fitted[:, 1],
      kind="linear",
      fill_value="extrapolate",
      bounds_error=False,
  )

  # Keep all amplitude points and interpolate frequency values
  combined_points = []
  for p in amp_points:
    combined_points.append(
        common_utils.ControlPoint(
            time=p.time,
            frequency=np.max([0, freq_interp(p.time)]),
            amplitude=p.amplitude,
            time_shift=p.time_shift,
        )
    )

  # Add selective frequency points
  for i in range(1, len(freq_points) - 1):
    current_freq_point = copy.deepcopy(freq_points[i])
    prev_freq_point = copy.deepcopy(freq_points[i-1])
    next_freq_point = copy.deepcopy(freq_points[i+1])
    cur_freq = current_freq_point.frequency
    prev_freq = prev_freq_point.frequency
    next_freq = next_freq_point.frequency
    cur_time = current_freq_point.time

    # if the frequency of the current point is perceived different from either
    # its previous or next point, consider add
    if not _is_within_jnd_db(
        cur_freq, next_freq, jnd_db=common_utils.AMPLITUDE_FREQUENCY_JND, c=20
    ) or not _is_within_jnd_db(
        cur_freq, prev_freq, jnd_db=common_utils.AMPLITUDE_FREQUENCY_JND, c=20
    ):

      kept_points_before = [
          p for p in combined_points if p.time <= current_freq_point.time
      ]
      kept_points_after = [
          p for p in combined_points if p.time >= current_freq_point.time
      ]

      if kept_points_before and kept_points_after:
        prev_kept_point = kept_points_before[-1]
        next_kept_point = kept_points_after[0]

        cur_amp = np.max([0, amp_interp(current_freq_point.time)])
        prev_kept_freq = np.max([0, freq_interp(prev_kept_point.time)])
        if pwle_type == "advanced_pwle":
          cur_freq_p_int = common_utils.perceived_intensity(cur_amp, cur_freq)
          prev_kept_p_int = common_utils.perceived_intensity(
              prev_kept_point.amplitude, prev_kept_freq
          )
        elif pwle_type == "basic_pwle":
          cur_freq_p_int = cur_amp
          prev_kept_p_int = prev_kept_point.amplitude
        else:
          raise ValueError("Invalid PWLE type: ", pwle_type)

        # if perceived intensity is similar to its previous kept point and also
        # really close to that point, do not add in this case, if its perceived
        # frequency is largely different from its previous or next frequency
        # control point, still add
        if (
            _is_within_jnd_db(
                cur_freq_p_int,
                prev_kept_p_int,
                jnd_db=common_utils.INTENSITY_JND,
                c=10,
            )
            and _is_within_jnd_db(
                cur_freq,
                next_freq,
                jnd_db=common_utils.AMPLITUDE_FREQUENCY_JND * 2,
                c=20,
            )
            and _is_within_jnd_db(
                cur_freq,
                prev_freq,
                jnd_db=common_utils.AMPLITUDE_FREQUENCY_JND * 2,
                c=20,
            )
            and 0
            < current_freq_point.time - prev_kept_point.time
            < common_utils.MIN_DURATION / 2
        ):
          continue

        # if duration gap > MIN_DURATION*2, enough to add a point in the between
        if (
            next_kept_point.time - prev_kept_point.time
            >= common_utils.MIN_DURATION * 2
        ):

          # Adjust current point time to ensure MIN_DURATION ms gap between both
          # previous and next point
          if (
              current_freq_point.time - prev_kept_point.time
              < common_utils.MIN_DURATION
          ):
            current_freq_point.time = (
                prev_kept_point.time + common_utils.MIN_DURATION
            )
            cur_freq = freq_interp(current_freq_point.time)
            cur_amp = amp_interp(current_freq_point.time)
          if (
              next_kept_point.time - current_freq_point.time
              < common_utils.MIN_DURATION
          ):
            current_freq_point.time = (
                next_kept_point.time - common_utils.MIN_DURATION
            )
            cur_freq = freq_interp(current_freq_point.time)
            cur_amp = amp_interp(current_freq_point.time)

          combined_points.append(
              common_utils.ControlPoint(
                  time=current_freq_point.time,
                  frequency=cur_freq,
                  amplitude=cur_amp,
                  time_shift=current_freq_point.time - cur_time,
              )
          )
          combined_points = sorted(
              combined_points, key=lambda point: point.time
          )

  _, unique_indices = np.unique(
      [p.time for p in combined_points], return_index=True
  )
  combined_points = [combined_points[i] for i in unique_indices]

  return combined_points


def extract_control_points(
    amp_envelope: np.ndarray,
    freq_envelope: np.ndarray,
    rate: int,
    pwle_type: str,
    error_threshold: float = 0.01,
) -> list[common_utils.ControlPoint]:
  """Extracts control points from the amplitude and frequency envelopes.

  Args:
    amp_envelope: Amplitude envelope of the signal.
    freq_envelope: Instantaneous frequency envelope of the signal.
    rate: Sampling rate of the signal.
    pwle_type: The type of PWLE. Either 'advanced_pwle' or 'basic_pwle'.
    error_threshold: The error threshold for Ramer-Douglas-Peucker algorithm.

  Returns:
    A list of ControlPoint.
  """
  amp_fitted_downsampled, freq_fitted_downsampled = (
      common_utils.preprocess_envelopes(amp_envelope, freq_envelope, rate)
  )

  all_amp_points = rdp(
      amp_fitted_downsampled,
      epsilon=error_threshold,
      point_type=common_utils.PointType.AMPLITUDE,
  )
  all_freq_points = rdp(
      freq_fitted_downsampled,
      epsilon=error_threshold,
      point_type=common_utils.PointType.FREQUENCY,
  )

  amp_points = rdp_with_min_distance(all_amp_points, pwle_type)

  combined_points = _combine_amp_freq_points_selective(
      amp_points,
      amp_fitted_downsampled,
      all_freq_points,
      freq_fitted_downsampled,
      pwle_type)

  # This step can be skipped since frequency point will be added only when
  # duration between its previous and next kept points > MIN_DURATION * 2
  # If the threshold is smaller than MIN_DURATION * 2, this step is necessary
  # control_points = rdp_with_min_distance(combined_points, pwle_type)

  control_points = combined_points

  control_points = common_utils.zero_amplitude_at_zero_frequency(
      control_points, freq_fitted_downsampled
  )
  control_points = common_utils.set_fist_last_point_amp_to_zero(control_points)
  logging.info("Number of control points: %d", len(control_points))

  common_utils.reject_invalid_waveform(
      control_points, time_shift_threshold=100, mean_freq_threshold=25
  )

  return control_points
