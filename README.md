# PCM to PWLE Conversion Tool

### Background

PCM (Pulse-Code Modulation) is a low-level digital representation haptic
waveform format that specifies the amplitude of the vibration at a given
sampling rate. The PCM haptic effects are highly dependent on specific hardware
and are hard to be ported across different devices.

PWLE (Piecewise-Linear Envelope) describes the envelope of the vibration using a
series of control points. Each control point specifies a target amplitude and
frequency at a particular point in time. Haptics HAL then uses these control
points to generate a waveform that is optimized for its specific hardware
capabilities while still adhering to the designer's intent.

PWLE is a more abstract, concise and flexible format for defining haptics
effects that is not tied to a specific type of hardware, and it will be an
essential part of the standard Android haptics file format.

The PCM to PWLE conversion tool converts arbitrary PCM haptic effects to PWLE
based haptics format without introducing perception distortion. It helps
designers auto convert PCM format to portable haptics format, achieving the
goal: design once, play everywhere.

### How to use the tool

Commandline examples for generating PWLE based haptics files:

```
$ pcm_to_pwle wav_files/v-10-23-1-21.wav test_pwle1.json
```

```
$ pcm_to_pwle --haptic_type=advanced_pwle_haptic ogg_files/bumps.ogg test_pwle2.json
```

Add `--loglevel` if you want to dump and inspect internal logs:

```
$ pcm_to_pwle wav_files/v-10-28-7-36.wav test_pwle3.json --loglevel=INFO
```
