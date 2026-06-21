#include "citevision/dual_pipeline.hpp"

namespace citevision {

DualPipeline::DualPipeline(const PipelineConfig& config, HealthStatus& status)
    : config_(config), status_(status), sampler_(config.source_fps, config.target_analysis_fps) {
    status_.current_sample_rate = sampler_.sample_rate();
}

void DualPipeline::set_source_fps(double source_fps) {
    if (source_fps > 0) {
        config_.source_fps = source_fps;
        sampler_.reconfigure(source_fps);
        status_.current_sample_rate = sampler_.sample_rate();
    }
}

void DualPipeline::process_frame(uint64_t frame_index) {
    status_.frames_ingested = frame_index + 1;

    if (should_analyze(frame_index)) {
        ++analyzed_;
        status_.frames_analyzed = analyzed_;
    }

    if (should_record(frame_index)) {
        ++recorded_;
        status_.frames_recorded = recorded_;
    }
}

bool DualPipeline::should_analyze(uint64_t frame_index) const {
    return sampler_.should_sample(frame_index);
}

bool DualPipeline::should_record(uint64_t frame_index) const {
    (void)frame_index;
    return true;
}

}  // namespace citevision
