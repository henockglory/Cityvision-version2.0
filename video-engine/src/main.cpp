#include "citevision/config.hpp"
#include "citevision/dual_pipeline.hpp"
#include "citevision/health_server.hpp"
#include "citevision/rtsp_ingest.hpp"

#include <csignal>
#include <cstdlib>
#include <iostream>
#include <string>
#include <thread>
#include <chrono>

namespace {
volatile std::sig_atomic_t g_running = 1;

void signal_handler(int) {
    g_running = 0;
}
}  // namespace

int main(int argc, char* argv[]) {
    citevision::PipelineConfig config;
    config.rtsp_url = "rtsp://127.0.0.1:8554/stream";

    if (argc > 1) {
        config.rtsp_url = argv[1];
    }
    if (const char* port = std::getenv("VIDEO_ENGINE_HEALTH_PORT")) {
        config.health_port = std::atoi(port);
    }

    std::signal(SIGINT, signal_handler);
#ifdef SIGTERM
    std::signal(SIGTERM, signal_handler);
#endif

    citevision::HealthStatus status;
    citevision::HealthServer health(config.health_port, status);
    health.start();

    citevision::DualPipeline pipeline(config, status);
    citevision::RtspIngest ingest(config.rtsp_url);

    std::cout << "Citévision Video Engine 2.0" << std::endl;
    std::cout << "RTSP: " << config.rtsp_url << std::endl;
    std::cout << "Health: http://0.0.0.0:" << config.health_port << "/health" << std::endl;

    while (g_running) {
        if (!ingest.is_connected()) {
            if (ingest.connect()) {
                status.rtsp_connected = true;
                std::cout << "RTSP connected (" << ingest.width() << "x"
                          << ingest.height() << ")" << std::endl;
            } else {
                status.rtsp_connected = false;
                std::this_thread::sleep_for(std::chrono::seconds(5));
                continue;
            }
        }

        if (!ingest.read_frame()) {
            std::cerr << "RTSP read error; reconnecting..." << std::endl;
            ingest.disconnect();
            status.rtsp_connected = false;
            std::this_thread::sleep_for(std::chrono::seconds(2));
            continue;
        }

        pipeline.process_frame(ingest.frame_count() - 1);
    }

    ingest.disconnect();
    health.stop();
    std::cout << "Video engine stopped." << std::endl;
    return 0;
}
