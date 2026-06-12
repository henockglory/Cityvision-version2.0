#pragma once

#include <atomic>
#include <functional>
#include <string>
#include <thread>

namespace cv {

struct HealthStatus {
    bool ingest_connected = false;
    int64_t frames_received = 0;
    double analysis_fps = 0.0;
    std::string camera_id;
    std::string version = "2.0.0";
};

class HealthServer {
public:
    HealthServer(int port, std::function<HealthStatus()> status_provider);
    ~HealthServer();

    void start();
    void stop();

private:
    int port_;
    std::function<HealthStatus()> status_provider_;
    std::atomic<bool> running_{false};
    std::thread server_thread_;
};

}  // namespace cv
