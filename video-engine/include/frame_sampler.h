#pragma once

namespace cv {

class AdaptiveFrameSampler {
public:
    explicit AdaptiveFrameSampler(double target_fps = 5.0);

    void set_target_fps(double fps);
    void set_load_factor(double factor);  // 0.0 - 1.0, higher = more loaded

    bool should_process(int64_t pts_us, int64_t last_processed_pts_us);

    double effective_fps() const { return effective_fps_; }

private:
    double target_fps_;
    double effective_fps_;
    double load_factor_;
    int64_t min_interval_us_;
};

}  // namespace cv
