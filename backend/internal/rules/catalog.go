package rules

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type CatalogTemplate struct {
	ID             string          `json:"id"`
	Name           string          `json:"name"`
	Description    string          `json:"description,omitempty"`
	Category       string          `json:"category"`
	Severity       string          `json:"severity"`
	Definition     json.RawMessage `json:"definition,omitempty"`
	ConfigSchema   json.RawMessage `json:"configSchema,omitempty"`
	RedirectTo     string          `json:"redirect_to,omitempty"`
	PartialStatus  string          `json:"partial_status,omitempty"`
	PartialReasonFR string         `json:"partial_reason_fr,omitempty"`
}

func LoadCatalog(dir string) ([]CatalogTemplate, error) {
	if dir == "" {
		dir = "../shared/rule-catalog"
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	names := make([]string, 0, len(entries))
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".json") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	var all []CatalogTemplate
	byID := make(map[string]CatalogTemplate)
	for _, name := range names {
		data, err := os.ReadFile(filepath.Join(dir, name))
		if err != nil {
			continue
		}
		var batch []CatalogTemplate
		if err := json.Unmarshal(data, &batch); err != nil {
			continue
		}
		for _, t := range batch {
			if t.RedirectTo != "" && len(t.Definition) == 0 && t.Name == "" {
				continue
			}
			if _, seen := byID[t.ID]; seen {
				continue
			}
			byID[t.ID] = t
			all = append(all, t)
		}
	}
	return all, nil
}
