package aimodels

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/google/uuid"
)

var (
	modelIDPattern    = regexp.MustCompile(`^[a-z][a-z0-9_]{1,48}$`)
	eventTypePattern  = regexp.MustCompile(`^[a-z][a-z0-9_]{1,64}$`)
)

const maxModelDownloadBytes = 256 << 20 // 256 MiB

type OrgModelEntry struct {
	ID                 string   `json:"id"`
	Task               string   `json:"task"`
	File               string   `json:"file"`
	Classes            []string `json:"classes"`
	PositiveClasses    []string `json:"positive_classes"`
	Behavior           string   `json:"behavior"`
	EventType          string   `json:"event_type"`
	SHA256             string   `json:"sha256,omitempty"`
	LabelFR            string   `json:"label_fr,omitempty"`
	LabelEN            string   `json:"label_en,omitempty"`
	AppliesTo          string   `json:"applies_to,omitempty"`
	InputSource        string   `json:"input_source,omitempty"`
	InputSize          int      `json:"input_size,omitempty"`
	Capability         string   `json:"capability,omitempty"`
	HumanDescriptionFR string   `json:"human_description_fr,omitempty"`
	HumanDescriptionEN string   `json:"human_description_en,omitempty"`
	ProbeOK            bool     `json:"probe_ok"`
	ProbeNotes         string   `json:"probe_notes,omitempty"`
}

type OrgModelsFile struct {
	Version int             `json:"version"`
	Models  []OrgModelEntry `json:"models"`
}

func OrgModelsRoot() string {
	if v := os.Getenv("ORG_MODELS_ROOT"); v != "" {
		return v
	}
	if v := os.Getenv("DATA_ROOT"); v != "" {
		return filepath.Join(v, "orgs")
	}
	return filepath.Join("data", "orgs")
}

func OrgModelsDir(orgID uuid.UUID) string {
	return filepath.Join(OrgModelsRoot(), orgID.String(), "ai-models")
}

func OrgModelsRegistryPath(orgID uuid.UUID) string {
	return filepath.Join(OrgModelsDir(orgID), "org-models.json")
}

func CustomRuleTemplateID(modelID string) string {
	return "tpl-custom-" + strings.TrimSpace(modelID)
}

func ValidateModelID(id string) error {
	id = strings.TrimSpace(id)
	if !modelIDPattern.MatchString(id) {
		return fmt.Errorf("invalid model id (use a-z, 0-9, _, start with letter, 2-49 chars)")
	}
	return nil
}

func ValidateEventType(eventType string) error {
	eventType = strings.TrimSpace(eventType)
	if !eventTypePattern.MatchString(eventType) {
		return fmt.Errorf("invalid event_type (snake_case, a-z, 0-9, _, 2-65 chars)")
	}
	return nil
}

func normalizeAppliesTo(v string) string {
	switch strings.TrimSpace(strings.ToLower(v)) {
	case "line", "both":
		return strings.TrimSpace(strings.ToLower(v))
	default:
		return "zone"
	}
}

func normalizeInputSource(v string) string {
	switch strings.TrimSpace(strings.ToLower(v)) {
	case "crop_zone", "full_frame":
		return strings.TrimSpace(strings.ToLower(v))
	default:
		return "crop_vehicle"
	}
}

// ValidateOrgModelEntry enforces required metadata before persisting an ONNX model.
func ValidateOrgModelEntry(entry *OrgModelEntry) error {
	if entry == nil {
		return fmt.Errorf("empty model entry")
	}
	if err := ValidateModelID(entry.ID); err != nil {
		return err
	}
	entry.Task = strings.TrimSpace(strings.ToLower(entry.Task))
	if entry.Task != "classification" && entry.Task != "detection" {
		return fmt.Errorf("task must be classification or detection")
	}
	entry.AppliesTo = normalizeAppliesTo(entry.AppliesTo)
	entry.InputSource = normalizeInputSource(entry.InputSource)
	if entry.InputSize <= 0 {
		if entry.Task == "classification" {
			entry.InputSize = 224
		} else {
			entry.InputSize = 640
		}
	}
	if strings.TrimSpace(entry.LabelFR) == "" {
		return fmt.Errorf("label_fr is required")
	}
	if strings.TrimSpace(entry.LabelEN) == "" {
		entry.LabelEN = entry.LabelFR
	}
	if strings.TrimSpace(entry.EventType) == "" {
		return fmt.Errorf("event_type is required")
	}
	if err := ValidateEventType(entry.EventType); err != nil {
		return err
	}
	if len(entry.Classes) < 2 {
		return fmt.Errorf("at least two classes are required")
	}
	if len(entry.PositiveClasses) == 0 {
		return fmt.Errorf("positive_classes is required (violation classes)")
	}
	for _, c := range entry.Classes {
		if c == "" {
			return fmt.Errorf("classes cannot contain empty strings")
		}
	}
	for _, p := range entry.PositiveClasses {
		found := false
		for _, c := range entry.Classes {
			if c == p {
				found = true
				break
			}
		}
		if !found {
			return fmt.Errorf("positive class %q must exist in classes", p)
		}
	}
	if entry.Capability == "" {
		entry.Capability = "beta"
	}
	if entry.Behavior == "" {
		entry.Behavior = "custom:" + entry.ID
	}
	if entry.HumanDescriptionFR == "" {
		entry.HumanDescriptionFR = entry.LabelFR
	}
	if entry.HumanDescriptionEN == "" {
		entry.HumanDescriptionEN = entry.LabelEN
	}
	return nil
}

// DownloadModelFromURL fetches an ONNX file with size and scheme guards.
func DownloadModelFromURL(ctx context.Context, rawURL string) (io.ReadCloser, int64, error) {
	rawURL = strings.TrimSpace(rawURL)
	if rawURL == "" {
		return nil, 0, fmt.Errorf("download_url is empty")
	}
	if !strings.HasPrefix(rawURL, "https://") && !strings.HasPrefix(rawURL, "http://") {
		return nil, 0, fmt.Errorf("download_url must start with http:// or https://")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return nil, 0, err
	}
	client := &http.Client{Timeout: 10 * time.Minute}
	resp, err := client.Do(req)
	if err != nil {
		return nil, 0, fmt.Errorf("download failed: %w", err)
	}
	if resp.StatusCode >= 300 {
		resp.Body.Close()
		return nil, 0, fmt.Errorf("download http %d", resp.StatusCode)
	}
	if resp.ContentLength > maxModelDownloadBytes {
		resp.Body.Close()
		return nil, 0, fmt.Errorf("download too large (max %d bytes)", maxModelDownloadBytes)
	}
	return resp.Body, resp.ContentLength, nil
}

// ProbeONNXStub performs a minimal integrity check before accepting an upload [J.87].
func ProbeONNXStub(path string) (bool, string) {
	lower := strings.ToLower(path)
	if !strings.HasSuffix(lower, ".onnx") && !strings.HasSuffix(lower, ".onnx.tmp") {
		return false, "extension must be .onnx"
	}
	info, err := os.Stat(path)
	if err != nil {
		return false, "stat failed"
	}
	if info.Size() < 64 {
		return false, "file too small for ONNX"
	}
	f, err := os.Open(path)
	if err != nil {
		return false, "read failed"
	}
	defer f.Close()
	buf := make([]byte, 512)
	n, _ := io.ReadFull(f, buf)
	if n < 64 {
		return false, "truncated ONNX payload"
	}
	return true, "onnx stub probe ok"
}

func LoadOrgModels(orgID uuid.UUID) ([]OrgModelEntry, error) {
	path := OrgModelsRegistryPath(orgID)
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	var f OrgModelsFile
	if err := json.Unmarshal(data, &f); err != nil {
		return nil, err
	}
	return f.Models, nil
}

func SaveOrgModels(orgID uuid.UUID, models []OrgModelEntry) error {
	dir := OrgModelsDir(orgID)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	payload, err := json.MarshalIndent(OrgModelsFile{Version: 1, Models: models}, "", "  ")
	if err != nil {
		return err
	}
	tmp := filepath.Join(dir, ".org-models.json.tmp")
	if err := os.WriteFile(tmp, payload, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, OrgModelsRegistryPath(orgID))
}

func UpsertOrgModel(orgID uuid.UUID, entry OrgModelEntry, onnxBytes io.Reader) (OrgModelEntry, error) {
	if err := ValidateOrgModelEntry(&entry); err != nil {
		return OrgModelEntry{}, err
	}
	dir := OrgModelsDir(orgID)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return OrgModelEntry{}, err
	}
	if entry.File == "" {
		entry.File = entry.ID + ".onnx"
	}
	dest := filepath.Join(dir, entry.File)
	tmp := dest + ".tmp"
	out, err := os.Create(tmp)
	if err != nil {
		return OrgModelEntry{}, err
	}
	h := sha256.New()
	w := io.MultiWriter(out, h)
	if _, err := io.Copy(w, onnxBytes); err != nil {
		out.Close()
		os.Remove(tmp)
		return OrgModelEntry{}, err
	}
	if err := out.Close(); err != nil {
		os.Remove(tmp)
		return OrgModelEntry{}, err
	}
	entry.SHA256 = hex.EncodeToString(h.Sum(nil))
	ok, notes := ProbeONNXStub(tmp)
	entry.ProbeOK = ok
	entry.ProbeNotes = notes
	if !ok {
		os.Remove(tmp)
		return OrgModelEntry{}, fmt.Errorf("onnx probe failed: %s", notes)
	}
	if err := os.Rename(tmp, dest); err != nil {
		return OrgModelEntry{}, err
	}
	models, _ := LoadOrgModels(orgID)
	replaced := false
	for i, m := range models {
		if m.ID == entry.ID {
			models[i] = entry
			replaced = true
			break
		}
	}
	if !replaced {
		models = append(models, entry)
	}
	if err := SaveOrgModels(orgID, models); err != nil {
		return OrgModelEntry{}, err
	}
	return entry, nil
}

func OrgModelHealthKey(id string) string {
	return id + "_model_loaded"
}
