#pragma once

#include <string>

namespace citevision {

struct PipelineConfig {
    std::string rtsp_url;
    int analysis_width = 640;
    int analysis_height = 480;
    int record_width = 1280;
    int record_height = 720;
    int health_port = 9000;
    double target_analysis_fps = 5.0;
    double source_fps = 30.0;
};

struct HealthStatus {
    bool rtsp_connected = false;
    uint64_t frames_ingested = 0;
    uint64_t frames_analyzed = 0;
    uint64_t frames_recorded = 0;
    double current_sample_rate = 1.0;
};

}  // namespace citevision
