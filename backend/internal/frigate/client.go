package frigate

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"strconv"
	"strings"
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

// CreateFace ensures a Frigate Face Library folder exists for name.
func (c *Client) CreateFace(ctx context.Context, name string) error {
	if strings.TrimSpace(name) == "" {
		return fmt.Errorf("face name required")
	}
	_, err := c.postJSON(ctx, "/api/faces/"+url.PathEscape(name)+"/create", map[string]interface{}{})
	return err
}

// RegisterFace uploads a face JPEG into Frigate's Face Library for name.
func (c *Client) RegisterFace(ctx context.Context, name string, jpeg []byte) error {
	if strings.TrimSpace(name) == "" {
		return fmt.Errorf("face name required")
	}
	if len(jpeg) == 0 {
		return fmt.Errorf("empty face image")
	}
	var buf bytes.Buffer
	w := multipart.NewWriter(&buf)
	part, err := w.CreateFormFile("file", "face.jpg")
	if err != nil {
		return err
	}
	if _, err := part.Write(jpeg); err != nil {
		return err
	}
	if err := w.Close(); err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/api/faces/"+url.PathEscape(name)+"/register", &buf)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", w.FormDataContentType())
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return fmt.Errorf("register face: %d %s", resp.StatusCode, string(b))
	}
	return nil
}

// RecognizeFace asks Frigate to identify a face JPEG against its Face Library.
func (c *Client) RecognizeFace(ctx context.Context, jpeg []byte) (map[string]interface{}, error) {
	if len(jpeg) == 0 {
		return nil, fmt.Errorf("empty face image")
	}
	var buf bytes.Buffer
	w := multipart.NewWriter(&buf)
	part, err := w.CreateFormFile("file", "face.jpg")
	if err != nil {
		return nil, err
	}
	if _, err := part.Write(jpeg); err != nil {
		return nil, err
	}
	if err := w.Close(); err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/api/faces/recognize", &buf)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", w.FormDataContentType())
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
	if resp.StatusCode >= 300 {
		return nil, fmt.Errorf("recognize face: %d %s", resp.StatusCode, string(b))
	}
	var out map[string]interface{}
	if err := json.Unmarshal(b, &out); err != nil {
		return map[string]interface{}{"raw": string(b)}, nil
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
