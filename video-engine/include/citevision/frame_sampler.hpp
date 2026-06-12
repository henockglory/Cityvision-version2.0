#pragma once

namespace citevision {

class FrameSampler {
public:
    FrameSampler(double source_fps, double target_fps);

    /// Returns true if this frame should be sampled for analysis.
    bool should_sample(uint64_t frame_index) const;

    double sample_rate() const { return sample_rate_; }

private:
    double source_fps_;
    double target_fps_;
    int interval_;
    double sample_rate_;
};

}  // namespace citevision
