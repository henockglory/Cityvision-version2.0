package evidence

// Package models shared evidence contract (see shared/schemas/evidence.json).

type BBox struct {
	X      float64 `json:"x,omitempty"`
	Y      float64 `json:"y,omitempty"`
	Width  float64 `json:"width,omitempty"`
	Height float64 `json:"height,omitempty"`
}

type Clip struct {
	URL         string  `json:"url,omitempty"`
	AssetID     string  `json:"asset_id,omitempty"`
	DurationSec float64 `json:"duration_sec,omitempty"`
	Mime        string  `json:"mime,omitempty"`
}

type Image struct {
	Role    string `json:"role"`
	URL     string `json:"url,omitempty"`
	AssetID string `json:"asset_id,omitempty"`
	Label   string `json:"label,omitempty"`
	Mime    string `json:"mime,omitempty"`
	BBox    *BBox  `json:"bbox,omitempty"`
}

type Package struct {
	Version  int                    `json:"version"`
	Clip     *Clip                  `json:"clip,omitempty"`
	Images   []Image                `json:"images,omitempty"`
	Metadata map[string]interface{} `json:"metadata,omitempty"`
}
