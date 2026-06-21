#include "citevision/frame_sampler.hpp"

#include <algorithm>
#include <cmath>

namespace citevision {

FrameSampler::FrameSampler(double source_fps, double target_fps)
    : source_fps_(source_fps), target_fps_(target_fps), interval_(1), sample_rate_(1.0) {
    reconfigure(source_fps);
}

void FrameSampler::reconfigure(double source_fps) {
    source_fps_ = source_fps;
    interval_ = 1;
    sample_rate_ = 1.0;
    if (source_fps_ > 0 && target_fps_ > 0) {
        interval_ = std::max(1, static_cast<int>(std::round(source_fps_ / target_fps_)));
        sample_rate_ = source_fps_ / interval_;
    }
}

bool FrameSampler::should_sample(uint64_t frame_index) const {
    return frame_index % static_cast<uint64_t>(interval_) == 0;
}

}  // namespace citevision
