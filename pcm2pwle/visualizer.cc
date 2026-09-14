#include "pcm2pwle/visualizer.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

#include "absl/container/flat_hash_map.h"
#include "absl/log/log.h"
#include "absl/strings/str_cat.h"
#include "pcm2pwle/common_utils.h"

// clang-format off
#define STB_IMAGE_WRITE_IMPLEMENTATION
#include "stb_image_write.h"
#define STB_TRUETYPE_IMPLEMENTATION
#include "stb_truetype.h"
// clang-format on

namespace pcm2pwle {

namespace {

struct PresetSpec {
  double durationMs;
  double freqFactor;
  double intensityFactor;
  std::string color;
  uint8_t r, g, b;
};

const absl::flat_hash_map<std::string, PresetSpec>& GetPresetSpecs() {
  static const auto* specs = new absl::flat_hash_map<std::string, PresetSpec>{
      {"TICK", {5.0, 3.0, 0.5, "orange", 255, 127, 14}},
      {"LOW_TICK", {12.0, 2.0 / 3.0, 0.125, "brown", 140, 86, 75}},
      {"CLICK", {12.0, 1.0, 1.0, "purple", 148, 103, 189}}};
  return *specs;
}

}  // namespace

std::vector<double> GeneratePcmFromPoints(
    const std::vector<ControlPoint>& points, int sampleRate,
    std::string_view pwleType, const std::vector<PresetEvent>& presets) {
  std::vector<double> samples;
  if (!points.empty() && points[0].time > 0.0) {
    int silentSamples = static_cast<int>(sampleRate * points[0].time / 1000.0);
    samples.resize(silentSamples, 0.0);
  }

  double phase = 0.0;

  if (points.size() >= 2) {
    for (size_t i = 1; i < points.size(); ++i) {
      const auto& start = points[i - 1];
      const auto& end = points[i];
      double durationMs = end.time - start.time;
      if (durationMs <= 0.0) continue;

      double aStart = start.amplitude.value_or(0.0);
      double aEnd = end.amplitude.value_or(0.0);
      double fStart = start.frequency.value_or(0.0);
      double fEnd = end.frequency.value_or(0.0);

      int segLen = static_cast<int>(sampleRate * durationMs / 1000.0);
      for (int j = 0; j < segLen; ++j) {
        double frac = static_cast<double>(j) / segLen;
        double a = aStart + (aEnd - aStart) * frac;
        double f = fStart + (fEnd - fStart) * frac;
        double phaseDelta = 2.0 * M_PI * f / sampleRate;
        samples.push_back(a * std::sin(phase));
        phase += phaseDelta;
      }
    }
  }

  if (!presets.empty()) {
    double baseResonantFreq = kPwleFreqProfile.resonantFrequencyHz;
    const auto& specs = GetPresetSpecs();

    for (const auto& preset : presets) {
      auto it = specs.find(preset.presetEnum);
      const auto& spec = (it != specs.end()) ? it->second : specs.at("CLICK");

      double durationMs = spec.durationMs;
      double freq = baseResonantFreq * spec.freqFactor;
      double intensity = preset.intensity * spec.intensityFactor;

      int startSample = static_cast<int>(preset.time / 1000.0 * sampleRate);
      int burstLen = static_cast<int>(durationMs / 1000.0 * sampleRate);
      int endSample = startSample + burstLen;

      if (endSample > static_cast<int>(samples.size())) {
        samples.resize(endSample, 0.0);
      }

      double phaseOffset = -M_PI * freq * (durationMs / 1000.0);
      double alpha = 0.5;
      int width = static_cast<int>(alpha * burstLen / 2.0);

      for (int n = 0; n < burstLen; ++n) {
        double t = static_cast<double>(n) / sampleRate;
        double burst =
            intensity * std::sin(2.0 * M_PI * freq * t + phaseOffset);
        double w = 1.0;
        if (width > 0) {
          if (n < width) {
            w = 0.5 * (1.0 + std::cos(M_PI * (n - width) / width));
          } else if (n >= burstLen - width) {
            w = 0.5 *
                (1.0 + std::cos(M_PI * (n - (burstLen - 1 - width)) / width));
          }
        }
        samples[startSample + n] = burst * w;
      }
    }
  }

  return samples;
}

namespace {

void DrawPixel(std::vector<uint8_t>& buf, int w, int h, int x, int y, uint8_t r,
               uint8_t g, uint8_t b) {
  if (x < 0 || x >= w || y < 0 || y >= h) return;
  int idx = (y * w + x) * 3;
  buf[idx] = r;
  buf[idx + 1] = g;
  buf[idx + 2] = b;
}

void DrawLine(std::vector<uint8_t>& buf, int w, int h, int x0, int y0, int x1,
              int y1, uint8_t r, uint8_t g, uint8_t b) {
  int dx = std::abs(x1 - x0);
  int dy = -std::abs(y1 - y0);
  int sx = x0 < x1 ? 1 : -1;
  int sy = y0 < y1 ? 1 : -1;
  int err = dx + dy;
  while (true) {
    DrawPixel(buf, w, h, x0, y0, r, g, b);
    if (x0 == x1 && y0 == y1) break;
    int e2 = 2 * err;
    if (e2 >= dy) {
      err += dy;
      x0 += sx;
    }
    if (e2 <= dx) {
      err += dx;
      y0 += sy;
    }
  }
}

void DrawRect(std::vector<uint8_t>& buf, int w, int h, int x, int y, int rw,
              int rh, uint8_t r, uint8_t g, uint8_t b, bool fill = false) {
  if (fill) {
    for (int j = y; j < y + rh; ++j) {
      for (int i = x; i < x + rw; ++i) {
        DrawPixel(buf, w, h, i, j, r, g, b);
      }
    }
  } else {
    DrawLine(buf, w, h, x, y, x + rw, y, r, g, b);
    DrawLine(buf, w, h, x + rw, y, x + rw, y + rh, r, g, b);
    DrawLine(buf, w, h, x + rw, y + rh, x, y + rh, r, g, b);
    DrawLine(buf, w, h, x, y + rh, x, y, r, g, b);
  }
}

unsigned char* g_ttf_buffer = nullptr;
stbtt_fontinfo g_font_info;
bool g_font_initialized = false;

void InitFont() {
  if (g_font_initialized) return;
  const char* font_paths[] = {"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                              "/usr/share/fonts/dejavu/DejaVuSans.ttf",
                              "/System/Library/Fonts/Helvetica.ttc",
                              "/System/Library/Fonts/Menlo.ttc",
                              "C:\\Windows\\Fonts\\arial.ttf",
                              "C:\\Windows\\Fonts\\consola.ttf"};
  FILE* f = nullptr;
  for (const char* path : font_paths) {
    f = fopen(path, "rb");
    if (f) break;
  }
  if (!f) return;

  fseek(f, 0, SEEK_END);
  long size = ftell(f);
  fseek(f, 0, SEEK_SET);
  g_ttf_buffer = new unsigned char[size];
  fread(g_ttf_buffer, 1, size, f);
  fclose(f);

  if (stbtt_InitFont(&g_font_info, g_ttf_buffer,
                     stbtt_GetFontOffsetForIndex(g_ttf_buffer, 0))) {
    g_font_initialized = true;
  }
}

void DrawText(std::vector<uint8_t>& buf, int w, int h, int x, int y,
              std::string_view str, uint8_t r, uint8_t g, uint8_t b) {
  InitFont();
  if (!g_font_initialized) {
    static bool warned = false;
    if (!warned) {
      LOG(WARNING) << "No valid System TTF font found; text labels will not be "
                      "visualized in PNG output. (Use .svg output for native "
                      "vector text instead!)";
      warned = true;
    }
    return;
  }

  float font_size = 14.0f;
  float scale = stbtt_ScaleForPixelHeight(&g_font_info, font_size);
  int ascent, descent, lineGap;
  stbtt_GetFontVMetrics(&g_font_info, &ascent, &descent, &lineGap);
  ascent = static_cast<int>(ascent * scale + 0.5f);

  int curX = x;
  for (char ch : str) {
    int advance, lsb;
    stbtt_GetCodepointHMetrics(&g_font_info, ch, &advance, &lsb);

    int w_bmp, h_bmp, xoff, yoff;
    unsigned char* bitmap = stbtt_GetCodepointBitmap(
        &g_font_info, 0, scale, ch, &w_bmp, &h_bmp, &xoff, &yoff);

    if (bitmap) {
      int draw_y = y + ascent + yoff;
      int draw_x = curX + xoff;
      for (int row = 0; row < h_bmp; ++row) {
        for (int col = 0; col < w_bmp; ++col) {
          unsigned char alpha = bitmap[row * w_bmp + col];
          if (alpha > 0) {
            int pixel_x = draw_x + col;
            int pixel_y = draw_y + row;
            if (pixel_x >= 0 && pixel_x < w && pixel_y >= 0 && pixel_y < h) {
              int idx = (pixel_y * w + pixel_x) * 3;
              buf[idx + 0] =
                  static_cast<uint8_t>((buf[idx + 0] * (255 - alpha) + r * alpha) / 255);
              buf[idx + 1] =
                  static_cast<uint8_t>((buf[idx + 1] * (255 - alpha) + g * alpha) / 255);
              buf[idx + 2] =
                  static_cast<uint8_t>((buf[idx + 2] * (255 - alpha) + b * alpha) / 255);
            }
          }
        }
      }
      stbtt_FreeBitmap(bitmap, 0);
    }
    curX += static_cast<int>(advance * scale + 0.5f);
  }
}

}  // namespace

bool RunVisualization(const VisualizerOptions& options) {
  if (options.pcmFile.empty() && options.pwleFile.empty()) {
    LOG(ERROR) << "Must provide --pcm or --pwle for visualization.";
    return false;
  }

  std::vector<double> pcmRaw;
  int rateRaw = 0;
  if (!options.pcmFile.empty()) {
    if (!LoadPcmFile(options.pcmFile, &pcmRaw, &rateRaw)) {
      LOG(ERROR) << "Failed to load PCM: " << options.pcmFile;
      return false;
    }
  }

  int sampleRate = options.sampleRate.value_or(rateRaw > 0 ? rateRaw : 48000);

  std::vector<std::vector<ControlPoint>> envelopes;
  std::string pwleType;
  std::vector<PresetEvent> presets;
  std::vector<double> pcmReconstructed;

  if (!options.pwleFile.empty()) {
    if (!ParseHapticsJson(options.pwleFile, &envelopes, &pwleType, &presets)) {
      LOG(ERROR) << "Failed to parse JSON: " << options.pwleFile;
      return false;
    }
    std::vector<ControlPoint> flatPoints;
    for (const auto& env : envelopes) {
      flatPoints.insert(flatPoints.end(), env.begin(), env.end());
    }
    pcmReconstructed =
        GeneratePcmFromPoints(flatPoints, sampleRate, pwleType, presets);
  }

  if (options.cropS > 0.0) {
    if (!pcmRaw.empty()) {
      int maxSamples = static_cast<int>(options.cropS * rateRaw);
      if (static_cast<int>(pcmRaw.size()) > maxSamples) {
        pcmRaw.resize(maxSamples);
      }
    }
    if (!pcmReconstructed.empty()) {
      int maxSamples = static_cast<int>(options.cropS * sampleRate);
      if (static_cast<int>(pcmReconstructed.size()) > maxSamples) {
        pcmReconstructed.resize(maxSamples);
      }
    }
  }

  int numPlots = 0;
  if (!pcmRaw.empty()) ++numPlots;
  if (!envelopes.empty() || !presets.empty()) ++numPlots;
  if (!pcmReconstructed.empty()) ++numPlots;

  if (numPlots == 0) {
    LOG(ERROR) << "Nothing to plot.";
    return false;
  }

  int width = 1200;
  int plotHeight = 350;
  int height = plotHeight * numPlots;

  std::vector<uint8_t> pixels(width * height * 3, 255);
  std::ostringstream svg;
  svg << "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"" << width
      << "\" height=\"" << height << "\" viewBox=\"0 0 " << width << " "
      << height << "\">\n";
  svg << "<rect width=\"100%\" height=\"100%\" fill=\"white\"/>\n";

  double maxT = 0.0;
  if (!pcmRaw.empty())
    maxT = std::max(maxT, pcmRaw.size() / static_cast<double>(rateRaw));
  if (!pcmReconstructed.empty())
    maxT = std::max(maxT,
                    pcmReconstructed.size() / static_cast<double>(sampleRate));
  for (const auto& env : envelopes) {
    for (const auto& pt : env) maxT = std::max(maxT, pt.time / 1000.0);
  }
  if (maxT <= 0.0) maxT = 1.0;

  int currPlot = 0;
  int padL = 80, padR = 80, padT = 40, padB = 40;
  int plotW = width - padL - padR;
  int plotH = plotHeight - padT - padB;

  auto MapX = [&](double t) {
    return padL + static_cast<int>((t / maxT) * plotW);
  };

  double maxFreq = 300.0;
  for (const auto& env : envelopes) {
    for (const auto& pt : env) {
      maxFreq = std::max(maxFreq, pt.frequency.value_or(0.0));
    }
  }

  auto DrawMarkers = [&](int yOff, int plotType) {
    // Zero line (middle of plot)
    int zeroY = yOff + padT + plotH / 2;
    svg << "<line x1=\"" << padL << "\" y1=\"" << zeroY << "\" x2=\""
        << padL + plotW << "\" y2=\"" << zeroY
        << "\" stroke=\"#ccc\" stroke-width=\"1\" stroke-dasharray=\"4\"/>\n";
    for (int x = padL; x <= padL + plotW; x += 10) {
      if (x + 5 <= padL + plotW)
        DrawLine(pixels, width, height, x, zeroY, x + 5, zeroY, 200, 200, 200);
    }

    // Y-axis markers
    if (plotType == 1) {  // PCM (-1 to 1)
      auto drawYTick = [&](double val, const std::string& label) {
        int py = yOff + padT + static_cast<int>((0.5 - val * 0.45) * plotH);
        svg << "<line x1=\"" << padL - 5 << "\" y1=\"" << py << "\" x2=\""
            << padL << "\" y2=\"" << py
            << "\" stroke=\"#333\" stroke-width=\"1\"/>\n";
        DrawLine(pixels, width, height, padL - 5, py, padL, py, 50, 50, 50);
        svg << "<text x=\"" << padL - 8 << "\" y=\"" << py + 4
            << "\" font-family=\"sans-serif\" font-size=\"10\" fill=\"#666\" "
               "text-anchor=\"end\">"
            << label << "</text>\n";
        int tw = label.length() * 6;
        DrawText(pixels, width, height, padL - 8 - tw, py - 4, label, 100, 100,
                 100);
      };

      drawYTick(1.0, "1.0");
      drawYTick(0.5, "0.5");
      drawYTick(0.0, "0.0");
      drawYTick(-0.5, "-0.5");
      drawYTick(-1.0, "-1.0");
    } else if (plotType == 2) {  // Envelopes (Amplitude & Frequency)
      auto drawYTickAmp = [&](double val, const std::string& label) {
        int py = yOff + padT + static_cast<int>((1.0 - val * 0.9) * plotH);
        svg << "<line x1=\"" << padL - 5 << "\" y1=\"" << py << "\" x2=\""
            << padL << "\" y2=\"" << py
            << "\" stroke=\"#ca2727\" stroke-width=\"1\"/>\n";
        DrawLine(pixels, width, height, padL - 5, py, padL, py, 214, 39, 40);
        svg << "<text x=\"" << padL - 8 << "\" y=\"" << py + 4
            << "\" font-family=\"sans-serif\" font-size=\"10\" "
               "fill=\"#ca2727\" text-anchor=\"end\">"
            << label << "</text>\n";
        int tw = label.length() * 6;
        DrawText(pixels, width, height, padL - 8 - tw, py - 4, label, 214, 39,
                 40);
      };

      drawYTickAmp(1.0, "1.0");
      drawYTickAmp(0.5, "0.5");
      drawYTickAmp(0.0, "0.0");

      auto drawYTickFreq = [&](double freqVal, const std::string& label) {
        int py = yOff + padT +
                 static_cast<int>((1.0 - (freqVal / maxFreq) * 0.9) * plotH);
        svg << "<line x1=\"" << padL + plotW << "\" y1=\"" << py << "\" x2=\""
            << padL + plotW + 5 << "\" y2=\"" << py
            << "\" stroke=\"#2ca02c\" stroke-width=\"1\"/>\n";
        DrawLine(pixels, width, height, padL + plotW, py, padL + plotW + 5, py,
                 44, 160, 44);
        svg << "<text x=\"" << padL + plotW + 8 << "\" y=\"" << py + 4
            << "\" font-family=\"sans-serif\" font-size=\"10\" "
               "fill=\"#2ca02c\" text-anchor=\"start\">"
            << label << "</text>\n";
        DrawText(pixels, width, height, padL + plotW + 8, py - 4, label, 44,
                 160, 44);
      };

      drawYTickFreq(maxFreq, absl::StrCat(static_cast<int>(maxFreq), "Hz"));
      drawYTickFreq(maxFreq * 0.5,
                    absl::StrCat(static_cast<int>(maxFreq * 0.5), "Hz"));
      drawYTickFreq(0.0, "0Hz");
    }

    // X-axis time markers (10 intervals)
    for (int i = 0; i <= 10; ++i) {
      double pct = i / 10.0;
      double t = pct * maxT;
      int px = padL + static_cast<int>(pct * plotW);
      int btmY = yOff + padT + plotH;
      // Tick line
      svg << "<line x1=\"" << px << "\" y1=\"" << btmY << "\" x2=\"" << px
          << "\" y2=\"" << btmY + 5
          << "\" stroke=\"#333\" stroke-width=\"1\"/>\n";
      DrawLine(pixels, width, height, px, btmY, px, btmY + 5, 50, 50, 50);

      char buf[32];
      snprintf(buf, sizeof(buf), "%.2fs", t);
      std::string tStr(buf);
      int tw = tStr.length() * 6;

      svg << "<text x=\"" << px << "\" y=\"" << btmY + 20
          << "\" font-family=\"sans-serif\" font-size=\"10\" fill=\"#666\" "
             "text-anchor=\"middle\">"
          << tStr << "</text>\n";
      DrawText(pixels, width, height, px - tw / 2, btmY + 18, tStr, 100, 100,
               100);
    }
  };

  // Plot 1: Raw PCM
  if (!pcmRaw.empty()) {
    int yOff = currPlot * plotHeight;
    DrawRect(pixels, width, height, padL, yOff + padT, plotW, plotH, 200, 200,
             200);
    svg << "<rect x=\"" << padL << "\" y=\"" << yOff + padT << "\" width=\""
        << plotW << "\" height=\"" << plotH
        << "\" fill=\"#fcfcfc\" stroke=\"#ccc\"/>\n";
    DrawMarkers(yOff, 1);

    std::string title1 =
        absl::StrCat("Raw PCM Data (sample_rate=", rateRaw, " Hz)");
    int len1 = title1.length() * 8;
    DrawText(pixels, width, height, padL + plotW / 2 - len1 / 2, yOff + 15,
             title1, 50, 50, 50);
    svg << "<text x=\"" << (padL + plotW / 2) << "\" y=\"" << yOff + 25
        << "\" font-family=\"sans-serif\" font-size=\"14\" "
           "font-weight=\"bold\" fill=\"#333\" text-anchor=\"middle\">"
        << title1 << "</text>\n";

    svg << "<path d=\"";
    int prevPx = -1, prevPy = -1;
    for (size_t i = 0; i < pcmRaw.size(); ++i) {
      double t = static_cast<double>(i) / rateRaw;
      int px = MapX(t);
      double val = std::clamp(pcmRaw[i], -1.0, 1.0);
      int py = yOff + padT + static_cast<int>((0.5 - val * 0.45) * plotH);
      if (i == 0) {
        svg << "M " << px << " " << py << " ";
      } else {
        svg << "L " << px << " " << py << " ";
      }
      if (prevPx != -1) {
        DrawLine(pixels, width, height, prevPx, prevPy, px, py, 31, 119, 180);
      }
      prevPx = px;
      prevPy = py;
    }
    svg << "\" fill=\"none\" stroke=\"#1f77b4\" stroke-width=\"1.2\"/>\n";
    ++currPlot;
  }

  // Plot 2: Haptics Envelopes & Presets
  if (!envelopes.empty() || !presets.empty()) {
    int yOff = currPlot * plotHeight;
    DrawRect(pixels, width, height, padL, yOff + padT, plotW, plotH, 200, 200,
             200);
    svg << "<rect x=\"" << padL << "\" y=\"" << yOff + padT << "\" width=\""
        << plotW << "\" height=\"" << plotH
        << "\" fill=\"#fcfcfc\" stroke=\"#ccc\"/>\n";
    DrawMarkers(yOff, 2);

    std::string title2 = absl::StrCat("Haptics JSON (", pwleType, ")");
    int len2 = title2.length() * 8;
    DrawText(pixels, width, height, padL + plotW / 2 - len2 / 2, yOff + 15,
             title2, 50, 50, 50);
    svg << "<text x=\"" << (padL + plotW / 2) << "\" y=\"" << yOff + 25
        << "\" font-family=\"sans-serif\" font-size=\"14\" "
           "font-weight=\"bold\" fill=\"#333\" text-anchor=\"middle\">"
        << title2 << "</text>\n";

    const auto& specs = GetPresetSpecs();
    for (const auto& pr : presets) {
      auto it = specs.find(pr.presetEnum);
      const auto& sp = (it != specs.end()) ? it->second : specs.at("CLICK");
      double t0 = pr.time / 1000.0;
      double t1 = t0 + sp.durationMs / 1000.0;
      int x0 = MapX(t0);
      int x1 = std::max(x0 + 2, MapX(t1));
      int barH =
          static_cast<int>(pr.intensity * sp.intensityFactor * plotH * 0.9);
      int y0 = yOff + padT + plotH - barH;
      DrawRect(pixels, width, height, x0, y0, x1 - x0, barH, sp.r, sp.g, sp.b,
               true);
      svg << "<rect x=\"" << x0 << "\" y=\"" << y0 << "\" width=\"" << (x1 - x0)
          << "\" height=\"" << barH << "\" fill=\"" << sp.color
          << "\" opacity=\"0.6\"/>\n";
    }

    for (const auto& env : envelopes) {
      if (env.empty()) continue;
      svg << "<path d=\"";
      int prevAx = -1, prevAy = -1;
      int prevFx = -1, prevFy = -1;
      for (size_t i = 0; i < env.size(); ++i) {
        double t = env[i].time / 1000.0;
        int px = MapX(t);
        double ampVal = env[i].amplitude.value_or(0.0);
        double freqVal = env[i].frequency.value_or(0.0);
        int pyAmp =
            yOff + padT + static_cast<int>((1.0 - ampVal * 0.9) * plotH);
        int pyFreq =
            yOff + padT +
            static_cast<int>((1.0 - (freqVal / maxFreq) * 0.9) * plotH);

        if (i == 0) {
          svg << "M " << px << " " << pyAmp << " ";
        } else {
          svg << "L " << px << " " << pyAmp << " ";
        }

        if (prevAx != -1) {
          DrawLine(pixels, width, height, prevAx, prevAy, px, pyAmp, 214, 39,
                   40);
          DrawLine(pixels, width, height, prevFx, prevFy, px, pyFreq, 44, 160,
                   44);
        }
        DrawRect(pixels, width, height, px - 2, pyAmp - 2, 5, 5, 214, 39, 40,
                 true);
        DrawRect(pixels, width, height, px - 2, pyFreq - 2, 5, 5, 44, 160, 44,
                 true);
        prevAx = px;
        prevAy = pyAmp;
        prevFx = px;
        prevFy = pyFreq;
      }
      svg << "\" fill=\"none\" stroke=\"#d62728\" stroke-width=\"2\"/>\n";
    }
    ++currPlot;
  }

  // Plot 3: Reconstructed PCM
  if (!pcmReconstructed.empty()) {
    int yOff = currPlot * plotHeight;
    DrawRect(pixels, width, height, padL, yOff + padT, plotW, plotH, 200, 200,
             200);
    svg << "<rect x=\"" << padL << "\" y=\"" << yOff + padT << "\" width=\""
        << plotW << "\" height=\"" << plotH
        << "\" fill=\"#fcfcfc\" stroke=\"#ccc\"/>\n";
    DrawMarkers(yOff, 1);

    std::string title3 =
        absl::StrCat("Reconstructed PCM (sample_rate=", sampleRate, " Hz)");
    int len3 = title3.length() * 8;
    DrawText(pixels, width, height, padL + plotW / 2 - len3 / 2, yOff + 15,
             title3, 50, 50, 50);
    svg << "<text x=\"" << (padL + plotW / 2) << "\" y=\"" << yOff + 25
        << "\" font-family=\"sans-serif\" font-size=\"14\" "
           "font-weight=\"bold\" fill=\"#333\" text-anchor=\"middle\">"
        << title3 << "</text>\n";

    svg << "<path d=\"";
    int prevPx = -1, prevPy = -1;
    for (size_t i = 0; i < pcmReconstructed.size(); ++i) {
      double t = static_cast<double>(i) / sampleRate;
      int px = MapX(t);
      double val = std::clamp(pcmReconstructed[i], -1.0, 1.0);
      int py = yOff + padT + static_cast<int>((0.5 - val * 0.45) * plotH);
      if (i == 0) {
        svg << "M " << px << " " << py << " ";
      } else {
        svg << "L " << px << " " << py << " ";
      }
      if (prevPx != -1) {
        DrawLine(pixels, width, height, prevPx, prevPy, px, py, 255, 127, 14);
      }
      prevPx = px;
      prevPy = py;
    }
    svg << "\" fill=\"none\" stroke=\"#ff7f0e\" stroke-width=\"1.2\"/>\n";
    ++currPlot;
  }

  svg << "</svg>\n";

  std::string outPath = options.outputFile;
  std::string ext = "";
  size_t dot = outPath.rfind('.');
  if (dot != std::string::npos) {
    ext = outPath.substr(dot);
    for (char& c : ext) {
      c = std::tolower(static_cast<unsigned char>(c));
    }
  }

  if (ext == ".svg") {
    std::ofstream out(outPath);
    if (!out.is_open()) return false;
    out << svg.str();
    out.close();
    LOG(INFO) << "Plot saved to " << outPath;
  } else if (ext == ".jpg" || ext == ".jpeg") {
    if (!stbi_write_jpg(outPath.c_str(), width, height, 3, pixels.data(), 90)) {
      LOG(ERROR) << "Failed to write JPEG: " << outPath;
      return false;
    }
    LOG(INFO) << "Plot saved to " << outPath;
  } else {
    // Default to PNG
    if (ext != ".png") {
      outPath += ".png";
    }
    if (!stbi_write_png(outPath.c_str(), width, height, 3, pixels.data(),
                        width * 3)) {
      LOG(ERROR) << "Failed to write PNG: " << outPath;
      return false;
    }
    LOG(INFO) << "Plot saved to " << outPath;
  }

  return true;
}

}  // namespace pcm2pwle
