#pragma once

#include <cstdint>

namespace citevision {

class FrameSampler {
public:
    FrameSampler(double source_fps, double target_fps);

    bool should_sample(uint64_t frame_index) const;
    double sample_rate() const { return sample_rate_; }
    // Recompute the decimation interval when the real source FPS becomes known
    // (e.g. after the stream connects and reports avg_frame_rate).
    void reconfigure(double source_fps);

private:
    double source_fps_;
    double target_fps_;
    int interval_;
    double sample_rate_;
};

}  // namespace citevision
