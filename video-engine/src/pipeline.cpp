#include "pipeline.h"

#include <cmath>

namespace citevision {

DualPipeline::DualPipeline(PipelineConfig config) : config_(std::move(config)) {}

void DualPipeline::on_frame_ingested() {
    ++stats_.frames_ingested;
}

bool DualPipeline::should_analyze(uint64_t frame_index) {
    const auto interval = static_cast<uint64_t>(
        std::max(1.0, std::round(30.0 / config_.analysis_fps)));
    return frame_index % interval == 0;
}

bool DualPipeline::should_record(uint64_t frame_index) {
  // Record at source rate throttled to ~15fps for 720p storage
    return frame_index % 2 == 0;
}

void DualPipeline::mark_analyzed() { ++stats_.frames_analyzed; }

void DualPipeline::mark_recorded() { ++stats_.frames_recorded; }

}  // namespace citevision
