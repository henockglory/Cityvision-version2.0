#pragma once

#include <string>

namespace citevision {

class RtspIngest {
public:
    explicit RtspIngest(std::string url);
    ~RtspIngest();

    bool connect();
    void disconnect();
    bool is_connected() const { return connected_; }

    /// Read next decoded frame. Returns false on EOF or error.
    bool read_frame();

    int width() const { return width_; }
    int height() const { return height_; }
    uint64_t frame_count() const { return frame_count_; }

private:
    std::string url_;
    bool connected_ = false;
    int width_ = 0;
    int height_ = 0;
    uint64_t frame_count_ = 0;

    void* format_ctx_ = nullptr;
    void* codec_ctx_ = nullptr;
    int video_stream_index_ = -1;
};

}  // namespace citevision
