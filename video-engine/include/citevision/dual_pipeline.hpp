#pragma once

#include "citevision/config.hpp"
#include "citevision/frame_sampler.hpp"
#include <cstdint>

namespace citevision {

class DualPipeline {
public:
    DualPipeline(const PipelineConfig& config, HealthStatus& status);

    void process_frame(uint64_t frame_index);
    bool should_analyze(uint64_t frame_index) const;
    bool should_record(uint64_t frame_index) const;
    // Apply the real source FPS detected at connect time to the sampler.
    void set_source_fps(double source_fps);

private:
    PipelineConfig config_;
    HealthStatus& status_;
    FrameSampler sampler_;
    uint64_t analyzed_ = 0;
    uint64_t recorded_ = 0;
};

}  // namespace citevision
