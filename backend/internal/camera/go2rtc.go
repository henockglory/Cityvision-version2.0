package camera

import (
	"context"
	"encoding/json"
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
	q.Set("name", name)
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

func (g *Go2RTCClient) PreviewForStream(name string) *StreamRegistration {
	return &StreamRegistration{
		Name:          name,
		PreviewHLS:    fmt.Sprintf("%s/api/stream.m3u8?src=%s", g.baseURL, url.QueryEscape(name)),
		PreviewWebRTC: fmt.Sprintf("%s/stream.html?src=%s&mode=webrtc", g.baseURL, url.QueryEscape(name)),
	}
}

// UnregisterStream removes a stream from go2rtc (best-effort; offline cameras may leave stale entries).
func (g *Go2RTCClient) UnregisterStream(ctx context.Context, name string) error {
	q := url.Values{}
	q.Set("src", name)
	reqURL := g.baseURL + "/api/streams?" + q.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, reqURL, nil)
	if err != nil {
		return err
	}
	resp, err := g.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 && resp.StatusCode != http.StatusNotFound {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("go2rtc delete stream: %s", string(b))
	}
	return nil
}

// DeleteStream is an alias for UnregisterStream used by the demo service.
func (g *Go2RTCClient) DeleteStream(ctx context.Context, name string) error {
	return g.UnregisterStream(ctx, name)
}

// StreamExists reports whether a stream name is currently registered in go2rtc.
func (g *Go2RTCClient) StreamExists(ctx context.Context, name string) bool {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, g.baseURL+"/api/streams", nil)
	if err != nil {
		return false
	}
	resp, err := g.client.Do(req)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return false
	}
	var streams map[string]json.RawMessage
	if err := json.NewDecoder(resp.Body).Decode(&streams); err != nil {
		return false
	}
	_, ok := streams[name]
	return ok
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
