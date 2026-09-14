cmake_minimum_required(VERSION 3.16)
project(pcm2pwle LANGUAGES CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
  pkg_check_modules(SndFile QUIET sndfile)
endif()

if(NOT SndFile_FOUND)
  find_package(SndFile QUIET)
endif()

if(NOT SndFile_FOUND AND NOT TARGET SndFile::sndfile)
  find_path(SndFile_INCLUDE_DIR sndfile.h)
  find_library(SndFile_LIBRARY NAMES sndfile sndfile-1)
  if(SndFile_INCLUDE_DIR AND SndFile_LIBRARY)
    set(SndFile_FOUND TRUE)
    set(SndFile_INCLUDE_DIRS ${SndFile_INCLUDE_DIR})
    set(SndFile_LIBRARIES ${SndFile_LIBRARY})
  endif()
endif()

find_path(POCKETFFT_INCLUDE_DIR pocketfft_hdronly.h
    PATHS ${CMAKE_CURRENT_SOURCE_DIR}/pcm2pwle
)
if(NOT POCKETFFT_INCLUDE_DIR)
  include(FetchContent)
  FetchContent_Declare(
      pocketfft
      GIT_REPOSITORY https://gitlab.mpcdf.mpg.de/mtr/pocketfft.git
      GIT_TAG        cpp
  )
  FetchContent_MakeAvailable(pocketfft)
  set(POCKETFFT_INCLUDE_DIR ${pocketfft_SOURCE_DIR})
endif()

find_path(STB_INCLUDE_DIR stb_image_write.h
    PATHS ${CMAKE_CURRENT_SOURCE_DIR}/pcm2pwle
)
if(NOT STB_INCLUDE_DIR)
  include(FetchContent)
  FetchContent_Declare(
      stb
      GIT_REPOSITORY https://github.com/nothings/stb.git
      GIT_TAG        master
  )
  FetchContent_MakeAvailable(stb)
  set(STB_INCLUDE_DIR ${stb_SOURCE_DIR})
endif()

find_package(absl CONFIG QUIET)
if(NOT absl_FOUND)
  include(FetchContent)
  FetchContent_Declare(
      abseil_cpp
      GIT_REPOSITORY https://github.com/abseil/abseil-cpp.git
      GIT_TAG        20260817.0
  )
  set(ABSL_PROPAGATE_CXX_SETTINGS ON CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(abseil_cpp)
endif()

set(PCM2PWLE_SRCS
    pcm2pwle/beating_detection.cc
    pcm2pwle/common_utils.cc
    pcm2pwle/control_point_extraction.cc
    pcm2pwle/converter.cc
    pcm2pwle/dsp_utils.cc
    pcm2pwle/frequency_amplitude_extraction.cc
    pcm2pwle/pcm2pwle_cc.cc
    pcm2pwle/preset_detection.cc
    pcm2pwle/visualizer.cc
)

add_executable(pcm2pwle ${PCM2PWLE_SRCS})

target_include_directories(pcm2pwle PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/pcm2pwle
    ${POCKETFFT_INCLUDE_DIR}
    ${STB_INCLUDE_DIR}
    ${SndFile_INCLUDE_DIRS}
)

target_link_libraries(pcm2pwle PRIVATE absl::strings absl::log absl::flat_hash_map absl::flags absl::flags_parse absl::log_initialize)

if(TARGET SndFile::sndfile)
  target_link_libraries(pcm2pwle PRIVATE SndFile::sndfile)
else()
  if(SndFile_LIBRARY_DIRS)
    target_link_directories(pcm2pwle PRIVATE ${SndFile_LIBRARY_DIRS})
  endif()
  target_link_libraries(pcm2pwle PRIVATE ${SndFile_LIBRARIES})
endif()

if(UNIX AND NOT APPLE)
  target_link_libraries(pcm2pwle PRIVATE m)
endif()

install(TARGETS pcm2pwle DESTINATION bin)
