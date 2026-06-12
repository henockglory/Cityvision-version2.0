#include "citevision/dual_pipeline.hpp"

namespace citevision {

DualPipeline::DualPipeline(const PipelineConfig& config, HealthStatus& status)
    : config_(config)
    , status_(status)
    , sampler_(config.source_fps, config.target_analysis_fps)
{
    status_.current_sample_rate = sampler_.sample_rate();
}

void DualPipeline::process_frame(uint64_t frame_index) {
    status_.frames_ingested = frame_index + 1;

    if (should_analyze(frame_index)) {
        ++analyzed_;
        status_.frames_analyzed = analyzed_;
        // Analysis path: downscale to analysis_width x analysis_height
        // (frame buffer passed to AI engine via shared memory / socket in production)
    }

    if (should_record(frame_index)) {
        ++recorded_;
        status_.frames_recorded = recorded_;
        // Recording path: encode at record_width x record_height (720p H.264)
    }
}

bool DualPipeline::should_analyze(uint64_t frame_index) const {
    return sampler_.should_sample(frame_index);
}

bool DualPipeline::should_record(uint64_t frame_index) const {
    // Record at full pipeline rate (every frame when source available)
    return true;
}

}  // namespace citevision
