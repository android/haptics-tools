#ifndef THIRD_PARTY_ANDROID_HAPTICS_TOOLS_PCM2PWLE_VISUALIZER_H_
#define THIRD_PARTY_ANDROID_HAPTICS_TOOLS_PCM2PWLE_VISUALIZER_H_

#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "pcm2pwle/common_utils.h"

namespace pcm2pwle {

struct VisualizerOptions {
  std::string pcmFile;
  std::string pwleFile;
  std::string outputFile;
  std::optional<int> sampleRate;
  double cropS = -1.0;
};

std::vector<double> GeneratePcmFromPoints(
    const std::vector<ControlPoint>& points, int sampleRate,
    std::string_view pwleType, const std::vector<PresetEvent>& presets = {});

bool RunVisualization(const VisualizerOptions& options);

}  // namespace pcm2pwle

#endif  // THIRD_PARTY_ANDROID_HAPTICS_TOOLS_PCM2PWLE_VISUALIZER_H_
