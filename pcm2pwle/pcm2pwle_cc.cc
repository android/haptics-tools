#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

#include "absl/log/initialize.h"
#include "absl/log/log.h"
#include "absl/flags/flag.h"
#include "absl/flags/usage.h"
#include "absl/flags/parse.h"


#include "pcm2pwle/converter.h"
#include "pcm2pwle/visualizer.h"

ABSL_FLAG(std::string, pcm, "", "Path to input PCM file (.wav or .ogg)");
ABSL_FLAG(std::string, output, "",
          "Path to output PWLE JSON or visualization file");
ABSL_FLAG(std::string, pwle_type, "basic_pwle",
          "Type of PWLE to generate (basic_pwle or advanced_pwle)");
ABSL_FLAG(double, crop_s, -1.0,
          "Time in seconds to crop the beginning of the file");
ABSL_FLAG(double, error_threshold, 0.01,
          "Error threshold for PWLE RDP extraction");
ABSL_FLAG(
    double, pulse_to_neighbor_ratio, 5.0,
    "Amplitude ratio threshold against neighbor max required for a pulse");
ABSL_FLAG(
    double, amp_ratio_threshold, 0.05,
    "Amplitude ratio threshold against absolute max required for a pulse");
ABSL_FLAG(double, preset_freq_threshold, 100.0,
          "Frequency threshold above which a pulse is considered a click "
          "rather than a thud");
ABSL_FLAG(std::string, pwle, "", "Path to PWLE JSON file for visualization");
ABSL_FLAG(std::string, xml, "", "Alias for --pwle");
ABSL_FLAG(int, sample_rate, 0, "Sample rate override for visualization");
ABSL_FLAG(std::vector<std::string>, freq_profile, {},
          "Comma-separated frequency profile: min,resonant,max");

int main(int argc, char* argv[]) {
  absl::SetProgramUsageMessage(
      "Usage:\n"
      "  pcm2pwle convert --pcm=<path> --output=<path> [options]\n"
      "  pcm2pwle visualize --output=<path> [--pcm=<path>] [--pwle=<path>] [options]");
  absl::InitializeLog();
  std::vector<char*> positional_args = absl::ParseCommandLine(argc, argv);

  if (positional_args.size() < 2) {
    std::cerr << "Usage:\n"
              << "  pcm2pwle convert --pcm=<path> --output=<path> [options]\n"
              << "  pcm2pwle visualize --output=<path> [--pcm=<path>] "
                 "[--pwle=<path>] [options]\n";
    return 1;
  }

  std::string command = positional_args[1];

  if (command == "visualize") {
    pcm2pwle::VisualizerOptions options;
    options.pcmFile = absl::GetFlag(FLAGS_pcm);
    options.pwleFile = absl::GetFlag(FLAGS_pwle);
    if (options.pwleFile.empty()) {
      options.pwleFile = absl::GetFlag(FLAGS_xml);
    }
    options.outputFile = absl::GetFlag(FLAGS_output);
    int sr = absl::GetFlag(FLAGS_sample_rate);
    if (sr > 0) {
      options.sampleRate = sr;
    }
    options.cropS = absl::GetFlag(FLAGS_crop_s);

    if (options.outputFile.empty()) {
      LOG(ERROR) << "--output is required for visualize.\n";
      return 1;
    }

    if (!pcm2pwle::RunVisualization(options)) {
      return 1;
    }
    return 0;
  }

  if (command != "convert") {
    std::cerr << "Available commands: convert, visualize\n";
    return 1;
  }

  pcm2pwle::ConversionOptions options;
  options.pcmFile = absl::GetFlag(FLAGS_pcm);
  options.outputFile = absl::GetFlag(FLAGS_output);
  options.pwleType = absl::GetFlag(FLAGS_pwle_type);
  options.cropS = absl::GetFlag(FLAGS_crop_s);
  options.errorThreshold = absl::GetFlag(FLAGS_error_threshold);
  options.pulseToNeighborRatio = absl::GetFlag(FLAGS_pulse_to_neighbor_ratio);
  options.ampRatioThreshold = absl::GetFlag(FLAGS_amp_ratio_threshold);
  options.presetFreqThreshold = absl::GetFlag(FLAGS_preset_freq_threshold);

  std::vector<std::string> prof = absl::GetFlag(FLAGS_freq_profile);
  if (!prof.empty()) {
    if (prof.size() == 3) {
      char* end;
      double min = std::strtod(prof[0].c_str(), &end);
      if (end == prof[0].c_str()) {
        LOG(ERROR) << "Invalid float in freq_profile\n";
        return 1;
      }

      double res = std::strtod(prof[1].c_str(), &end);
      if (end == prof[1].c_str()) {
        LOG(ERROR) << "Invalid float in freq_profile\n";
        return 1;
      }

      double max = std::strtod(prof[2].c_str(), &end);
      if (end == prof[2].c_str()) {
        LOG(ERROR) << "Invalid float in freq_profile\n";
        return 1;
      }

      options.freqProfile.minFrequencyHz = min;
      options.freqProfile.resonantFrequencyHz = res;
      options.freqProfile.maxFrequencyHz = max;
    } else {
      LOG(ERROR) << "--freq_profile must have exactly 3 comma-separated "
                    "numbers (min,resonant,max).\n";
      return 1;
    }
  }

  if (options.pcmFile.empty() || options.outputFile.empty()) {
    LOG(ERROR) << "--pcm and --output are required.\n";
    return 1;
  }

  if (!pcm2pwle::RunConversion(options)) {
    return 1;
  }

  return 0;
}
