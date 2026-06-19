#include "citevision/health_server.hpp"

#include <iostream>
#include <sstream>
#include <string>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
using socket_t = SOCKET;
#define CLOSE_SOCKET closesocket
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
using socket_t = int;
#define CLOSE_SOCKET close
#define INVALID_SOCKET (-1)
#endif

namespace citevision {

HealthServer::HealthServer(int port, HealthStatus& status)
    : port_(port), status_(status) {}

HealthServer::~HealthServer() {
    stop();
}

void HealthServer::start() {
    if (running_) return;
    running_ = true;
    thread_ = std::thread(&HealthServer::serve, this);
}

void HealthServer::stop() {
    running_ = false;
    if (thread_.joinable()) {
        thread_.join();
    }
}

std::string HealthServer::json_response(const HealthStatus& status) {
    std::ostringstream oss;
    oss << "{"
        << "\"status\":\"ok\","
        << "\"service\":\"citevision-video-engine\","
        << "\"rtsp_connected\":" << (status.rtsp_connected ? "true" : "false") << ","
        << "\"frames_ingested\":" << status.frames_ingested << ","
        << "\"frames_analyzed\":" << status.frames_analyzed << ","
        << "\"frames_recorded\":" << status.frames_recorded << ","
        << "\"current_sample_rate\":" << status.current_sample_rate
        << "}";
    return oss.str();
}

void HealthServer::serve() {
#ifdef _WIN32
    WSADATA wsa;
    WSAStartup(MAKEWORD(2, 2), &wsa);
#endif

    socket_t server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd == INVALID_SOCKET) {
        std::cerr << "Health server: socket creation failed" << std::endl;
        return;
    }

    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR,
               reinterpret_cast<const char*>(&opt), sizeof(opt));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(static_cast<uint16_t>(port_));

    if (bind(server_fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        std::cerr << "Health server: bind failed on port " << port_ << std::endl;
        CLOSE_SOCKET(server_fd);
        return;
    }

    if (listen(server_fd, 4) < 0) {
        CLOSE_SOCKET(server_fd);
        return;
    }

    std::cout << "Health server listening on : " << port_ << std::endl;

    while (running_) {
        fd_set read_set;
        FD_ZERO(&read_set);
        FD_SET(server_fd, &read_set);

        timeval tv{};
        tv.tv_sec = 1;
        tv.tv_usec = 0;

        int activity = select(static_cast<int>(server_fd) + 1, &read_set, nullptr, nullptr, &tv);
        if (activity <= 0) continue;

        socket_t client = accept(server_fd, nullptr, nullptr);
        if (client == INVALID_SOCKET) continue;

        char buffer[1024] = {};
        recv(client, buffer, sizeof(buffer) - 1, 0);

        std::string body = json_response(status_);
        std::ostringstream response;
        response << "HTTP/1.1 200 OK\r\n"
                 << "Content-Type: application/json\r\n"
                 << "Content-Length: " << body.size() << "\r\n"
                 << "Connection: close\r\n\r\n"
                 << body;

        std::string resp = response.str();
        send(client, resp.c_str(), static_cast<int>(resp.size()), 0);
        CLOSE_SOCKET(client);
    }

    CLOSE_SOCKET(server_fd);
#ifdef _WIN32
    WSACleanup();
#endif
}

}  // namespace citevision
