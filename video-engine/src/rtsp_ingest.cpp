#include "citevision/rtsp_ingest.hpp"

extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
}

#include <iostream>

namespace citevision {

RtspIngest::RtspIngest(std::string url) : url_(std::move(url)) {}

RtspIngest::~RtspIngest() {
    disconnect();
}

bool RtspIngest::connect() {
    avformat_network_init();

    auto* fmt = avformat_alloc_context();
    format_ctx_ = fmt;

    AVDictionary* opts = nullptr;
    av_dict_set(&opts, "rtsp_transport", "tcp", 0);
    av_dict_set(&opts, "stimeout", "10000000", 0);

    if (avformat_open_input(&fmt, url_.c_str(), nullptr, &opts) < 0) {
        std::cerr << "Failed to open RTSP stream: " << url_ << std::endl;
        av_dict_free(&opts);
        return false;
    }
    av_dict_free(&opts);

    if (avformat_find_stream_info(fmt, nullptr) < 0) {
        std::cerr << "Failed to find stream info" << std::endl;
        return false;
    }

    video_stream_index_ = -1;
    for (unsigned i = 0; i < fmt->nb_streams; ++i) {
        if (fmt->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_VIDEO) {
            video_stream_index_ = static_cast<int>(i);
            break;
        }
    }

    if (video_stream_index_ < 0) {
        std::cerr << "No video stream found" << std::endl;
        return false;
    }

    auto* par = fmt->streams[video_stream_index_]->codecpar;
    width_ = par->width;
    height_ = par->height;

    const AVCodec* codec = avcodec_find_decoder(par->codec_id);
    if (!codec) {
        std::cerr << "Decoder not found" << std::endl;
        return false;
    }

    auto* ctx = avcodec_alloc_context3(codec);
    codec_ctx_ = ctx;
    avcodec_parameters_to_context(ctx, par);

    if (avcodec_open2(ctx, codec, nullptr) < 0) {
        std::cerr << "Failed to open codec" << std::endl;
        return false;
    }

    connected_ = true;
    return true;
}

void RtspIngest::disconnect() {
    if (codec_ctx_) {
        avcodec_free_context(reinterpret_cast<AVCodecContext**>(&codec_ctx_));
        codec_ctx_ = nullptr;
    }
    if (format_ctx_) {
        avformat_close_input(reinterpret_cast<AVFormatContext**>(&format_ctx_));
        format_ctx_ = nullptr;
    }
    connected_ = false;
}

bool RtspIngest::read_frame() {
    if (!connected_) return false;

    auto* fmt = static_cast<AVFormatContext*>(format_ctx_);
    auto* ctx = static_cast<AVCodecContext*>(codec_ctx_);
    AVPacket* packet = av_packet_alloc();
    AVFrame* frame = av_frame_alloc();
    bool got_frame = false;

    while (av_read_frame(fmt, packet) >= 0) {
        if (packet->stream_index != video_stream_index_) {
            av_packet_unref(packet);
            continue;
        }

        if (avcodec_send_packet(ctx, packet) >= 0) {
            if (avcodec_receive_frame(ctx, frame) >= 0) {
                ++frame_count_;
                got_frame = true;
                break;
            }
        }
        av_packet_unref(packet);
    }

    av_frame_free(&frame);
    av_packet_free(&packet);
    return got_frame;
}

}  // namespace citevision
