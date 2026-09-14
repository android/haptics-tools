#include "pcm2pwle/converter.h"

#include <iostream>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <variant>
#include <vector>

#include "absl/log/log.h"
#include "pcm2pwle/beating_detection.h"
#include "pcm2pwle/common_utils.h"
#include "pcm2pwle/control_point_extraction.h"
#include "pcm2pwle/frequency_amplitude_extraction.h"
#include "pcm2pwle/preset_detection.h"

namespace pcm2pwle {

std::pair<std::vector<std::variant<BasicPwlePoint, AdvancedPwlePoint>>,
          std::vector<std::pair<double, double>>>
RunPcmToHapticsConversion(const std::vector<double>& pcmRaw, int rate,
                          std::string_view pwleType,
                          const ConversionOptions& options) {
  std::optional<double> cropSec = std::nullopt;
  if (options.cropS > 0.0) {
    cropSec = options.cropS;
  }
  std::vector<double> pcmPreprocessed =
      VibDataPreprocess(pcmRaw, rate, 500.0, cropSec);
  std::vector<double> pcmPreprocessedCopy = pcmPreprocessed;

  auto [ampEnvelope, freqEnvelope] =
      ExtractVibAmpFreq(pcmPreprocessed, rate, 100.0);

  auto detectedPresets = DetectPresets(
      ampEnvelope, freqEnvelope, rate, options.pulseToNeighborRatio,
      options.ampRatioThreshold, options.presetFreqThreshold);

  if (!detectedPresets.empty()) {
    pcmPreprocessed =
        SilencePcmAtPresets(pcmPreprocessed, detectedPresets, rate);
    auto reextracted = ExtractVibAmpFreq(pcmPreprocessed, rate, 100.0);
    ampEnvelope = reextracted.first;
    freqEnvelope = reextracted.second;
  }

  auto beatingFreqs = IsBeating(pcmRaw, rate);

  std::vector<ControlPoint> controlPoints;
  if (beatingFreqs.has_value()) {
    controlPoints =
        ExtractBeatingControlPoints(ampEnvelope, freqEnvelope, *beatingFreqs,
                                    rate, pwleType, options.errorThreshold);
  } else {
    controlPoints = ExtractControlPoints(ampEnvelope, freqEnvelope, rate,
                                         pwleType, options.errorThreshold);
  }

  std::vector<std::variant<BasicPwlePoint, AdvancedPwlePoint>> pwlePoints;
  if (pwleType == "advanced_pwle") {
    auto advPoints = GenerateAdvancedPwle(controlPoints);
    for (const auto& p : advPoints) {
      pwlePoints.push_back(p);
    }
  } else {
    auto basicPoints = GenerateBasicPwle(controlPoints, options.freqProfile);
    for (const auto& p : basicPoints) {
      pwlePoints.push_back(p);
    }
  }

  auto presetInsertPoints =
      CalculatePresetInsertPoints(pcmPreprocessedCopy, detectedPresets, rate);

  return {pwlePoints, presetInsertPoints};
}

bool RunConversion(const ConversionOptions& options) {
  std::vector<double> data;
  int sampleRate = 0;
  if (!LoadPcmFile(options.pcmFile, &data, &sampleRate)) {
    LOG(ERROR) << "Error loading PCM file: " << options.pcmFile;
    return false;
  }

  auto [pwlePoints, presetInsertPoints] =
      RunPcmToHapticsConversion(data, sampleRate, options.pwleType, options);

  return !GeneratePwleJson(pwlePoints, options.pwleType, options.outputFile,
                           "2.0", presetInsertPoints)
              .empty();
}

}  // namespace pcm2pwle
