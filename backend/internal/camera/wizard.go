package camera

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/citevision/citevision-v2/backend/internal/models"
)

type ProbeRequest struct {
	Host     string `json:"host"`
	Port     int    `json:"port"`
	Channel  int    `json:"channel"`
	Username string `json:"username"`
	Password string `json:"password"`
	Vendor   string `json:"vendor"`
}

type ProbeCandidate struct {
	Vendor    string `json:"vendor"`
	Profile   string `json:"profile"`
	RTSPPath  string `json:"rtsp_path,omitempty"`
	URL       string `json:"url"`
	OK        bool   `json:"ok"`
	Reachable bool   `json:"reachable,omitempty"`
	VideoOK   bool   `json:"video_ok,omitempty"`
	LatencyMS int64  `json:"latency_ms,omitempty"`
	Error     string `json:"error,omitempty"`
}

type ProbeResult struct {
	Host       string           `json:"host"`
	Best       *ProbeCandidate  `json:"best,omitempty"`
	Candidates []ProbeCandidate `json:"candidates"`
	Ffprobe    *FfprobeResult   `json:"ffprobe,omitempty"` // nil when best is nil or ffprobe not installed
}

func DefaultProbePaths(vendor string, channel int) []struct {
	Vendor  string
	Profile string
	Path    string
} {
	switch vendor {
	case "hikvision":
		return []struct {
			Vendor, Profile, Path string
		}{
			{"hikvision", "main", ""},
			{"hikvision", "sub", ""},
		}
	case "dahua":
		return []struct {
			Vendor, Profile, Path string
		}{
			{"dahua", "main", ""},
			{"dahua", "sub", ""},
		}
	default:
		return []struct {
			Vendor, Profile, Path string
		}{
			{"generic", "main", "/live"},
			{"dahua", "main", ""},
			{"generic", "main", "/cam/realmonitor?channel=1&subtype=0"},
			{"hikvision", "main", ""},
			{"generic", "main", "/stream"},
			{"generic", "main", "/h264"},
			{"generic", "main", "/Streaming/Channels/101"},
		}
	}
}

func ProbeCredentials(ctx context.Context, req ProbeRequest, timeout time.Duration) ProbeResult {
	if req.Port == 0 {
		req.Port = 554
	}
	if req.Channel == 0 {
		req.Channel = 1
	}
	if timeout == 0 {
		timeout = 8 * time.Second
	}

	vendor := req.Vendor
	if vendor == "" || vendor == "auto" {
		vendor = "auto"
	}

	paths := DefaultProbePaths(vendor, req.Channel)
	result := ProbeResult{Host: req.Host, Candidates: make([]ProbeCandidate, 0, len(paths))}

	var best *ProbeCandidate
	for _, p := range paths {
		select {
		case <-ctx.Done():
			result.Best = best
			return result
		default:
		}

		url := BuildRTSPURL(p.Vendor, req.Host, req.Port, req.Channel, req.Username, req.Password, p.Path, p.Profile)
		test := TestStream(ctx, url, timeout)
		cand := ProbeCandidate{
			Vendor:    p.Vendor,
			Profile:   p.Profile,
			RTSPPath:  p.Path,
			URL:       MaskRTSP(url),
			Reachable: test.Reachable,
			VideoOK:   test.VideoOK,
			OK:        test.VideoOK,
			LatencyMS: test.LatencyMS,
			Error:     test.Error,
		}
		result.Candidates = append(result.Candidates, cand)
		if cand.OK && (best == nil || cand.LatencyMS < best.LatencyMS) {
			copy := cand
			best = &copy
			// Chemin vidéo validé — pas besoin d'essayer les autres URLs
			break
		}
	}
	result.Best = best
	// ffprobe détaillé sur le meilleur candidat (codec, résolution)
	if best != nil {
		ffURL := BuildRTSPURL(best.Vendor, req.Host, req.Port, req.Channel, req.Username, req.Password, best.RTSPPath, best.Profile)
		ffResult := ProbeStreamFfprobe(ctx, ffURL, 12*time.Second)
		result.Ffprobe = &ffResult
	}
	return result
}

func WizardCreateFromProbe(req ProbeRequest, best ProbeCandidate, orgID, siteID uuid.UUID, name string) CreateRequest {
	vendor := models.VendorGeneric
	switch best.Vendor {
	case "hikvision":
		vendor = models.VendorHikvision
	case "dahua":
		vendor = models.VendorDahua
	}
	return CreateRequest{
		OrgID:         orgID,
		SiteID:        siteID,
		Name:          name,
		Vendor:        vendor,
		Host:          req.Host,
		Port:          req.Port,
		Channel:       req.Channel,
		Username:      req.Username,
		Password:      req.Password,
		RTSPPath:      best.RTSPPath,
		StreamProfile: best.Profile,
	}
}

func ValidateProbe(req ProbeRequest) error {
	if req.Host == "" {
		return fmt.Errorf("host is required")
	}
	if req.Username == "" {
		return fmt.Errorf("username is required")
	}
	return nil
}
