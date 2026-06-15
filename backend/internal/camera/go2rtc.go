package camera

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"time"
)

type Go2RTCClient struct {
	baseURL string
	client  *http.Client
}

func NewGo2RTCClient() *Go2RTCClient {
	base := os.Getenv("GO2RTC_URL")
	if base == "" {
		base = "http://localhost:1984"
	}
	return &Go2RTCClient{
		baseURL: base,
		client:  &http.Client{Timeout: 10 * time.Second},
	}
}

type StreamRegistration struct {
	Name     string `json:"name"`
	RTSPURL  string `json:"rtsp_url"`
	PreviewHLS string `json:"preview_hls"`
	PreviewWebRTC string `json:"preview_webrtc"`
}

func (g *Go2RTCClient) RegisterStream(ctx context.Context, name, rtspURL string) (*StreamRegistration, error) {
	q := url.Values{}
	q.Set("dst", name)
	q.Set("src", rtspURL)
	reqURL := g.baseURL + "/api/streams?" + q.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodPut, reqURL, nil)
	if err != nil {
		return nil, err
	}

	resp, err := g.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("go2rtc unreachable: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("go2rtc register failed: %s", string(b))
	}

	return &StreamRegistration{
		Name:          name,
		RTSPURL:       MaskRTSP(rtspURL),
		PreviewHLS:    fmt.Sprintf("%s/api/stream.m3u8?src=%s", g.baseURL, url.QueryEscape(name)),
		PreviewWebRTC: fmt.Sprintf("%s/stream.html?src=%s&mode=webrtc", g.baseURL, url.QueryEscape(name)),
	}, nil
}

func (g *Go2RTCClient) Health(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, g.baseURL+"/api", nil)
	if err != nil {
		return err
	}
	resp, err := g.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return fmt.Errorf("go2rtc unhealthy status %d", resp.StatusCode)
	}
	return nil
}
