#pragma once

#include <cstdint>
#include <string>

namespace citevision {

struct PipelineConfig {
    std::string camera_id;
    int analysis_width{640};
    int analysis_height{480};
    int record_width{1280};
    int record_height{720};
    double analysis_fps{5.0};
};

struct PipelineStats {
    uint64_t frames_ingested{0};
    uint64_t frames_analyzed{0};
    uint64_t frames_recorded{0};
    double last_fps{0.0};
    bool healthy{true};
};

/// Dual pipeline: low-res analysis stream + 720p recording stream.
class DualPipeline {
public:
    explicit DualPipeline(PipelineConfig config);

    void on_frame_ingested();
    bool should_analyze(uint64_t frame_index);
    bool should_record(uint64_t frame_index);

    void mark_analyzed();
    void mark_recorded();

    const PipelineConfig& config() const { return config_; }
    const PipelineStats& stats() const { return stats_; }

private:
    PipelineConfig config_;
    PipelineStats stats_;
};

}  // namespace citevision
