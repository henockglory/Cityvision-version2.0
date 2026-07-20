package camera

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
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
		baseURL: strings.TrimRight(base, "/"),
		client:  &http.Client{Timeout: 15 * time.Second},
	}
}

type StreamRegistration struct {
	Name          string `json:"name"`
	RTSPURL       string `json:"rtsp_url"`
	PreviewHLS    string `json:"preview_hls"`
	PreviewWebRTC string `json:"preview_webrtc"`
	Healed        bool   `json:"healed,omitempty"`
	Transcode     bool   `json:"transcode,omitempty"`
}

func (g *Go2RTCClient) RegisterStream(ctx context.Context, name, rtspURL string) (*StreamRegistration, error) {
	return g.RegisterStreamSources(ctx, name, []string{rtspURL})
}

// RegisterStreamSources registers a stream with ordered failover sources.
// Uses query-param PUT first (reliable on go2rtc 1.9); JSON body only for multi-source.
func (g *Go2RTCClient) RegisterStreamSources(ctx context.Context, name string, sources []string) (*StreamRegistration, error) {
	if name == "" || len(sources) == 0 {
		return nil, fmt.Errorf("name and sources required")
	}
	_ = g.UnregisterStream(ctx, name)

	registerQuery := func(src string) error {
		q := url.Values{}
		q.Set("name", name)
		q.Set("src", src)
		req, err := http.NewRequestWithContext(ctx, http.MethodPut, g.baseURL+"/api/streams?"+q.Encode(), nil)
		if err != nil {
			return err
		}
		resp, err := g.client.Do(req)
		if err != nil {
			return fmt.Errorf("go2rtc unreachable: %w", err)
		}
		defer resp.Body.Close()
		if resp.StatusCode >= 300 {
			b, _ := io.ReadAll(resp.Body)
			return fmt.Errorf("go2rtc register failed: %s", string(b))
		}
		return nil
	}

	primary := sources[0]
	if len(sources) == 1 {
		if err := registerQuery(primary); err != nil {
			return nil, err
		}
	} else {
		// Multi-source: try JSON array; fall back to primary query if go2rtc rejects or stream missing.
		body, _ := json.Marshal(sources)
		reqURL := g.baseURL + "/api/streams?name=" + url.QueryEscape(name)
		req, err := http.NewRequestWithContext(ctx, http.MethodPut, reqURL, bytes.NewReader(body))
		if err != nil {
			return nil, err
		}
		req.Header.Set("Content-Type", "application/json")
		resp, err := g.client.Do(req)
		if err != nil {
			return nil, fmt.Errorf("go2rtc unreachable: %w", err)
		}
		bodyBytes, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		ok := resp.StatusCode < 300
		if ok {
			// go2rtc sometimes returns 200 without persisting JSON body — verify.
			time.Sleep(100 * time.Millisecond)
			if !g.StreamExists(ctx, name) {
				ok = false
			}
		}
		if !ok {
			if err := registerQuery(primary); err != nil {
				return nil, fmt.Errorf("go2rtc register failed: %s / fallback: %w", string(bodyBytes), err)
			}
		}
	}

	if !g.StreamExists(ctx, name) {
		// Last resort: re-PUT primary via query
		if err := registerQuery(primary); err != nil {
			return nil, err
		}
		if !g.StreamExists(ctx, name) {
			return nil, fmt.Errorf("go2rtc register reported ok but stream %q missing", name)
		}
	}

	return &StreamRegistration{
		Name:          name,
		RTSPURL:       MaskRTSP(primary),
		PreviewHLS:    fmt.Sprintf("%s/api/stream.m3u8?src=%s", g.baseURL, url.QueryEscape(name)),
		PreviewWebRTC: fmt.Sprintf("%s/stream.html?src=%s&mode=webrtc", g.baseURL, url.QueryEscape(name)),
		Transcode:     strings.HasPrefix(primary, "ffmpeg:"),
	}, nil
}

func (g *Go2RTCClient) PreviewForStream(name string) *StreamRegistration {
	return &StreamRegistration{
		Name:          name,
		PreviewHLS:    fmt.Sprintf("%s/api/stream.m3u8?src=%s", g.baseURL, url.QueryEscape(name)),
		PreviewWebRTC: fmt.Sprintf("%s/stream.html?src=%s&mode=webrtc", g.baseURL, url.QueryEscape(name)),
	}
}

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

func (g *Go2RTCClient) DeleteStream(ctx context.Context, name string) error {
	return g.UnregisterStream(ctx, name)
}

func (g *Go2RTCClient) StreamExists(ctx context.Context, name string) bool {
	streams, err := g.ListStreams(ctx)
	if err != nil {
		return false
	}
	_, ok := streams[name]
	return ok
}

func (g *Go2RTCClient) ListStreams(ctx context.Context) (map[string]json.RawMessage, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, g.baseURL+"/api/streams", nil)
	if err != nil {
		return nil, err
	}
	resp, err := g.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("go2rtc streams status %d", resp.StatusCode)
	}
	var streams map[string]json.RawMessage
	if err := json.NewDecoder(resp.Body).Decode(&streams); err != nil {
		return nil, err
	}
	return streams, nil
}

// PreviewHealth describes whether a go2rtc stream is safe for browser WebRTC.
type PreviewHealth struct {
	OK           bool   `json:"ok"`
	NeedsHeal    bool   `json:"needs_heal"`
	Reason       string `json:"reason,omitempty"`
	HasProducer  bool   `json:"has_producer"`
	Codec        string `json:"codec,omitempty"`
	UnsafeCodec  bool   `json:"unsafe_codec"`
}

// InspectPreviewHealth parses go2rtc stream JSON for HEVC / missing producers.
func InspectPreviewHealth(raw json.RawMessage) PreviewHealth {
	h := PreviewHealth{OK: false, NeedsHeal: true, Reason: "empty"}
	if len(raw) == 0 {
		return h
	}
	s := strings.ToLower(string(raw))
	if IsCodecErrorMessage(s) {
		return PreviewHealth{NeedsHeal: true, Reason: "codec_error_in_stream", UnsafeCodec: true}
	}
	var obj map[string]interface{}
	if err := json.Unmarshal(raw, &obj); err != nil {
		return PreviewHealth{NeedsHeal: true, Reason: "parse_error"}
	}
	producers, _ := obj["producers"].([]interface{})
	if len(producers) == 0 {
		return PreviewHealth{NeedsHeal: true, Reason: "no_producers"}
	}
	h.HasProducer = true
	codec := ""
	for _, p := range producers {
		pm, _ := p.(map[string]interface{})
		if pm == nil {
			continue
		}
		if urlStr, _ := pm["url"].(string); strings.Contains(strings.ToLower(urlStr), "hevc") {
			return PreviewHealth{HasProducer: true, NeedsHeal: true, Reason: "hevc_url", UnsafeCodec: true, Codec: "hevc"}
		}
		if src, _ := pm["source"].(string); strings.Contains(strings.ToLower(src), "[hevc") {
			return PreviewHealth{HasProducer: true, NeedsHeal: true, Reason: "hevc_ffmpeg", UnsafeCodec: true, Codec: "hevc"}
		}
		medias, _ := pm["medias"].([]interface{})
		for _, m := range medias {
			ms, _ := m.(string)
			ml := strings.ToLower(ms)
			if strings.Contains(ml, "hevc") || strings.Contains(ml, "h265") {
				return PreviewHealth{HasProducer: true, NeedsHeal: true, Reason: "hevc_media", UnsafeCodec: true, Codec: "hevc"}
			}
			if strings.Contains(ml, "h264") {
				codec = "h264"
			}
		}
		receivers, _ := pm["receivers"].([]interface{})
		for _, r := range receivers {
			rm, _ := r.(map[string]interface{})
			if rm == nil {
				continue
			}
			c, _ := rm["codec"].(map[string]interface{})
			if c != nil {
				name, _ := c["codec_name"].(string)
				name = strings.ToLower(name)
				if name == "hevc" || name == "h265" {
					return PreviewHealth{HasProducer: true, NeedsHeal: true, Reason: "hevc_receiver", UnsafeCodec: true, Codec: name}
				}
				if name == "h264" {
					codec = "h264"
				}
			}
		}
	}
	if codec == "h264" {
		return PreviewHealth{OK: true, HasProducer: true, Codec: "h264"}
	}
	// Producer present but codec unknown — heal to force ffmpeg h264.
	return PreviewHealth{HasProducer: true, NeedsHeal: true, Reason: "codec_unknown", Codec: codec}
}

func (g *Go2RTCClient) GetPreviewHealth(ctx context.Context, name string) PreviewHealth {
	streams, err := g.ListStreams(ctx)
	if err != nil {
		return PreviewHealth{NeedsHeal: true, Reason: "go2rtc_unreachable"}
	}
	raw, ok := streams[name]
	if !ok {
		return PreviewHealth{NeedsHeal: true, Reason: "missing"}
	}
	return InspectPreviewHealth(raw)
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
