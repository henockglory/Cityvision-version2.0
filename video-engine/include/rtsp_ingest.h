#pragma once

#include <string>

namespace cv {

struct IngestConfig {
    std::string rtsp_url;
    std::string camera_id;
    int reconnect_delay_ms = 3000;
    int read_timeout_ms = 5000;
};

struct IngestStats {
    int64_t frames_received = 0;
    int64_t frames_dropped = 0;
    bool connected = false;
    std::string last_error;
};

class RtspIngest {
public:
    explicit RtspIngest(IngestConfig config);
    ~RtspIngest();

    bool open();
    void close();
    bool read_frame(uint8_t* buffer, int buffer_size, int& width, int& height, int64_t& pts);

    const IngestStats& stats() const { return stats_; }

private:
    IngestConfig config_;
    IngestStats stats_;
    void* format_ctx_ = nullptr;
    void* codec_ctx_ = nullptr;
    int video_stream_index_ = -1;
};

}  // namespace cv
