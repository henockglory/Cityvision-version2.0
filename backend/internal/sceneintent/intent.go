package sceneintent

import "encoding/json"

// Intent is the unified zone↔règle contract [K.93].
type Intent struct {
	CameraID  string          `json:"camera_id,omitempty"`
	Spatial   SpatialBinding  `json:"spatial"`
	Detection DetectionConfig `json:"detection"`
	Alerting  AlertingConfig  `json:"alerting"`
	Models    []string        `json:"models,omitempty"`
}

type SpatialBinding struct {
	Name     string          `json:"name"`
	Type     string          `json:"type"` // zone | line
	Geometry json.RawMessage `json:"geometry,omitempty"`
}

type DetectionConfig struct {
	Behavior    string                 `json:"behavior"`
	Config      map[string]interface{} `json:"config,omitempty"`
	ClassFilter string                 `json:"class_filter,omitempty"`
}

type AlertingConfig struct {
	TemplateID string          `json:"template_id,omitempty"`
	Threshold  json.RawMessage `json:"threshold,omitempty"`
	Evidence   json.RawMessage `json:"evidence,omitempty"`
	Mail       bool            `json:"mail,omitempty"`
}

type ValidationResult struct {
	Valid   bool     `json:"valid"`
	Errors  []string `json:"errors,omitempty"`
	Warnings []string `json:"warnings,omitempty"`
}
