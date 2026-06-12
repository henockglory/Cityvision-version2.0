#pragma once

#include "citevision/config.hpp"
#include <atomic>
#include <thread>

namespace citevision {

class HealthServer {
public:
    HealthServer(int port, HealthStatus& status);
    ~HealthServer();

    void start();
    void stop();

private:
    int port_;
    HealthStatus& status_;
    std::atomic<bool> running_{false};
    std::thread thread_;

    void serve();
    static std::string json_response(const HealthStatus& status);
};

}  // namespace citevision
