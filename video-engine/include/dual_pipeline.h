#pragma once

#include <cstdint>
#include <string>

namespace cv {

struct PipelineConfig {
    std::string camera_id;
    int analysis_width = 640;
    int analysis_height = 480;
    int record_width = 1280;
    int record_height = 720;
    int record_bitrate_kbps = 2000;
    std::string record_output_dir = "/data/recordings";
};

struct PipelineStats {
    int64_t analysis_frames = 0;
    int64_t record_frames = 0;
    int64_t skipped_frames = 0;
    double current_analysis_fps = 0.0;
};

class DualPipeline {
public:
    explicit DualPipeline(PipelineConfig config);

    void on_frame(const uint8_t* src, int src_width, int src_height, int64_t pts);
    void tick(double delta_seconds);

    const PipelineStats& stats() const { return stats_; }
    const PipelineConfig& config() const { return config_; }

private:
    PipelineConfig config_;
    PipelineStats stats_;
    int64_t last_analysis_pts_ = -1;
    double analysis_interval_ = 0.2;  // 5 fps default
};

}  // namespace cv
