#!/bin/bash

# This script verifies the output of pcm2pwle against golden files. The binary
# is built using CMake.
#
# 1. Temporarily change the origin to piper.presubmit_origin() in copy.bara.sky
# (do not check in the change), and dry run copybara push to a temp folder:
# /google/bin/releases/copybara/public/copybara/copybara third_party/android/haptics_tools/copy.bara.sky push_to_github [PENDING_CL_NUMBER] --dry-run --git-destination-path /tmp/haptics_tools
# 2. Copy the verification_cli.sh script to the local temp folder:
# cp third_party/android/haptics_tools/pcm2pwle/verification.sh /tmp/haptics_tools/verification.sh
# and change the `ROOT_FOLDER` to your google3 root.
# 3. Go to the temp folder, and run the script.
# Examples:
#   bash verification_cli.sh --pwle_type basic --file_type ogg
#   bash verification_cli.sh --pwle_type advanced --file_type wav

# The root folder of the google3 directory
# This should be set to your google3 root, e.g., /google/src/cloud/$USER/<client_name>/google3

ROOT_FOLDER=""
PWLE_ARG="advanced"
FILE_TYPE="ogg"

while [[ "$#" -gt 0 ]]; do
  case $1 in
    --pwle_type)
      PWLE_ARG="$2"
      shift
      ;;
    --file_type)
      FILE_TYPE="$2"
      shift
      ;;
    *)
      echo "Unknown parameter passed: $1"
      exit 1
      ;;
  esac
  shift
done

if [[ -z "${ROOT_FOLDER}" ]]; then
  echo "Error: ROOT_FOLDER is not set."
  exit 1
fi
echo "Using ROOT_FOLDER: ${ROOT_FOLDER}"

PCM_DIR="${ROOT_FOLDER}/third_party/android/haptics_tools/pcm2pwle"

if [[ "${FILE_TYPE}" == "ogg" ]]; then
  SOURCE_FOLDER="${PCM_DIR}/ogg_files"
  EXTRA_ARGS="--crop_s=2"
elif [[ "${FILE_TYPE}" == "wav" ]]; then
  SOURCE_FOLDER="${PCM_DIR}/wav_files"
  EXTRA_ARGS=""
else
  echo "Error: Unsupported file type '${FILE_TYPE}'"
  exit 1
fi

if [[ "${PWLE_ARG}" == "basic" ]]; then
  PWLE_TYPE="basic_pwle"
  THRESHOLD=3e-4
  GOLDEN_FOLDER="${PCM_DIR}/basic_pwle_golden"
  OUTPUT_FOLDER="pwle_basic_cli_output"
elif [[ "${PWLE_ARG}" == "advanced" ]]; then
  PWLE_TYPE="advanced_pwle"
  THRESHOLD=5e-3
  GOLDEN_FOLDER="${PCM_DIR}/advanced_pwle_golden"
  OUTPUT_FOLDER="pwle_advanced_cli_output"
else
  echo "Error: Unsupported pwle_type '${PWLE_ARG}'"
  exit 1
fi

BINARY="build/pcm2pwle"

if [ -f "$BINARY" ]; then
  echo "Found existing binary at $BINARY. Skipping compilation."
else
  echo "Compiling C++ pcm2pwle binary via CMake ..."
  (cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build --config Release)
  if [ $? -ne 0 ]; then
    echo "Error: Compilation failed. Exiting."
    exit 1
  fi
  echo "Compilation successful."
fi

if [[ ! -d "${SOURCE_FOLDER}" ]]; then
  echo "Error: source folder '${SOURCE_FOLDER}' not found."
  exit 1
fi

if [[ ! -d "${GOLDEN_FOLDER}" ]]; then
  echo "Error: golden folder '${GOLDEN_FOLDER}' not found."
  exit 1
fi

if [[ ! -d "${OUTPUT_FOLDER}" ]]; then
  echo "Creating output folder '${OUTPUT_FOLDER}'..."
  mkdir -p "${OUTPUT_FOLDER}"
fi

echo "Starting processing in ${SOURCE_FOLDER}..."

find "${SOURCE_FOLDER}" -maxdepth 1 -type f | sort | \
  while IFS= read -r filepath; do
  if [[ -n "$filepath" ]]; then
    filename=$(basename "$filepath")

    echo "--------------------------------------------------"
    echo "Processing: $filename"

    output_filename="${filename//-/_}"
    output_filename="${OUTPUT_FOLDER}_${output_filename}"
    output_filename="${output_filename%.*}.json"

    # Golden follows standard pwle_basic prefix regardless of test output directory.
    if [[ "${PWLE_ARG}" == "basic" ]]; then
      golden_filename="${filename//-/_}"
      golden_filename="pwle_basic_${golden_filename}"
      golden_filename="${golden_filename%.*}.xml"
    else
      golden_filename="${filename//-/_}"
      golden_filename="pwle_advanced_${golden_filename}"
      golden_filename="${golden_filename%.*}.xml"
    fi

    start_time=$(date +%s)

    "${BINARY}" convert --pwle_type="${PWLE_TYPE}" ${EXTRA_ARGS} \
      --pcm="${SOURCE_FOLDER}/$filename" \
      --output="${OUTPUT_FOLDER}/${output_filename}"

    if [ $? -ne 0 ]; then
      echo "Error: Conversion failed for file '$filename'"
    else
      echo "Successful conversion for file '$filename'"
      end_time=$(date +%s)
      elapsed=$((end_time - start_time))
      echo ">>>>>>>>>>  Processing time: $elapsed seconds."

      # Support dynamic JSON vs XML checking as requested during Google CL transition!
      python3 -c "
import sys
import json
import xml.etree.ElementTree as ET

def parse_file(path):
    nums = []
    try:
        with open(path) as f:
            d = json.load(f)
            events = d.get('hapticEffect', {}).get('events', [])
            for event in events:
                for k, v in event.items():
                    if k in ('basicEnvelope', 'advancedEnvelope'):
                        if 'initialSharpness' in v:
                            nums.append(float(v['initialSharpness']))
                        if 'initialFrequency' in v:
                            nums.append(float(v['initialFrequency']))
                        for cp in v.get('controlPoint', []):
                            for attr in ('durationMillis', 'intensity', 'sharpness', 'amplitude', 'frequencyHz'):
                                if attr in cp:
                                    nums.append(float(cp[attr]))
        return nums
    except:
        pass
    
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        for ev in root.findall('.//event'):
            for env in ev:
                if 'initialSharpness' in env.attrib:
                    nums.append(float(env.attrib['initialSharpness']))
                if 'initialFrequency' in env.attrib:
                    nums.append(float(env.attrib['initialFrequency']))
                for cp in env.findall('.//controlPoint'):
                    for attr in ('durationMillis', 'intensity', 'sharpness', 'amplitude', 'frequencyHz'):
                        if attr in cp.attrib:
                            nums.append(float(cp.attrib[attr]))
    except Exception as e:
        print(f'Critical XML error reading {path}: {e}')
    return nums

p1 = sys.argv[1]
p2 = sys.argv[2]
threshold = float(sys.argv[3])
n1 = parse_file(p1)
n2 = parse_file(p2)

if len(n1) == 0 or len(n2) == 0:
    print(f'Failed to parse numbers. len1={len(n1)}, len2={len(n2)}')
    sys.exit(1)

if len(n1) != len(n2):
    print(f'Length mismatch. output={len(n1)}, golden={len(n2)}')
    sys.exit(1)
    
for i, (v1, v2) in enumerate(zip(n1, n2)):
    abs_diff = abs(v1 - v2)
    max_val = max(abs(v1), abs(v2))
    rel_diff = abs_diff / max_val if max_val > 1e-9 else abs_diff
    if rel_diff > threshold:
        print(f'Threshold exceeded at index {i}. {v1} vs {v2}')
        sys.exit(1)
sys.exit(0)
" "${OUTPUT_FOLDER}/${output_filename}" "${GOLDEN_FOLDER}/${golden_filename}" "$THRESHOLD"

      if [ $? -eq 0 ]; then
        echo "  ✅ Files are identical."
      else
        echo "  ⚠️  Files are different under tolerance."
      fi
    fi
  fi
done

echo "Processing complete."
rm -rf "$OUTPUT_FOLDER"
