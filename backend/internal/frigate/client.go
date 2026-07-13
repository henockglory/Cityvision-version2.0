package frigate

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"time"
)

// Client wraps the Frigate HTTP API.
type Client struct {
	baseURL    string
	httpClient *http.Client
}

func NewClient(baseURL string) *Client {
	return &Client{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

func (c *Client) Version(ctx context.Context) (map[string]interface{}, error) {
	return c.getJSON(ctx, "/api/version")
}

func (c *Client) Reload(ctx context.Context) error {
	_, err := c.postJSON(ctx, "/api/restart", nil)
	return err
}

func (c *Client) Snapshot(ctx context.Context, cameraID string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/api/"+cameraID+"/latest.jpg", nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return nil, fmt.Errorf("snapshot %s: %d %s", cameraID, resp.StatusCode, string(body))
	}
	return io.ReadAll(resp.Body)
}

// ExportRecording requests a clip export centred on start/end unix timestamps.
func (c *Client) ExportRecording(ctx context.Context, cameraID string, start, end float64) (map[string]interface{}, error) {
	path := fmt.Sprintf("/api/events/%s/%s/clip.mp4?start_time=%.3f&end_time=%.3f", cameraID, cameraID, start, end)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+path, nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return nil, fmt.Errorf("export clip: %d %s", resp.StatusCode, string(body))
	}
	var out map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return map[string]interface{}{"status": "ok"}, nil
	}
	return out, nil
}

func (c *Client) DownloadClip(ctx context.Context, cameraID string, start, end float64) ([]byte, error) {
	path := fmt.Sprintf("/api/%s/recordings/%.0f/%.0f/clip.mp4", cameraID, start, end)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+path, nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return nil, fmt.Errorf("download clip: %d %s", resp.StatusCode, string(body))
	}
	return io.ReadAll(resp.Body)
}

func (c *Client) Ping(ctx context.Context) error {
	_, err := c.Version(ctx)
	return err
}

// ListEvents returns recent Frigate events (newest first when limit>0).
func (c *Client) ListEvents(ctx context.Context, cameraID string, limit int) ([]map[string]interface{}, error) {
	path := "/api/events?limit=" + strconv.Itoa(limit)
	if cameraID != "" {
		path += "&cameras=" + cameraID
	}
	raw, err := c.getJSONArray(ctx, path)
	if err != nil {
		return nil, err
	}
	return raw, nil
}

func (c *Client) getJSONArray(ctx context.Context, path string) ([]map[string]interface{}, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+path, nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return nil, fmt.Errorf("GET %s: %d %s", path, resp.StatusCode, string(body))
	}
	var out []map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) getJSON(ctx context.Context, path string) (map[string]interface{}, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+path, nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return nil, fmt.Errorf("GET %s: %d %s", path, resp.StatusCode, string(body))
	}
	var out map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return map[string]interface{}{"raw": "ok"}, nil
	}
	return out, nil
}

func (c *Client) postJSON(ctx context.Context, path string, body interface{}) (map[string]interface{}, error) {
	var r io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		r = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, r)
	if err != nil {
		return nil, err
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return nil, fmt.Errorf("POST %s: %d %s", path, resp.StatusCode, string(b))
	}
	var out map[string]interface{}
	_ = json.NewDecoder(resp.Body).Decode(&out)
	return out, nil
}
