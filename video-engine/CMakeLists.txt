cmake_minimum_required(VERSION 3.16)
project(citevision_video_engine VERSION 2.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(PkgConfig REQUIRED)
pkg_check_modules(FFMPEG REQUIRED
    libavformat
    libavcodec
    libavutil
    libswscale
)

add_executable(citevision-video-engine
    src/main.cpp
    src/rtsp_ingest.cpp
    src/dual_pipeline.cpp
    src/frame_sampler.cpp
    src/health_server.cpp
)

target_include_directories(citevision-video-engine PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${FFMPEG_INCLUDE_DIRS}
)

target_link_libraries(citevision-video-engine PRIVATE ${FFMPEG_LIBRARIES})

if(WIN32)
    target_link_libraries(citevision-video-engine PRIVATE ws2_32)
endif()

install(TARGETS citevision-video-engine DESTINATION bin)
