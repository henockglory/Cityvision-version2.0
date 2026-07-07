package syncrules

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/citevision/citevision-v2/rules-engine/internal/evaluator"
)

type dbRule struct {
	ID         string          `json:"id"`
	Name       string          `json:"name"`
	IsEnabled  bool            `json:"is_enabled"`
	Definition json.RawMessage `json:"definition"`
}

// PollActiveRules refreshes evaluator rules from the backend API on an interval.
func PollActiveRules(orgID, backendURL, apiKey string, interval time.Duration, apply func([]evaluator.RuleDefinition)) {
	if backendURL == "" || apiKey == "" {
		log.Printf("rules sync disabled: set BACKEND_API_URL, INTERNAL_API_KEY")
		return
	}
	urlAll := strings.TrimRight(backendURL, "/") + "/api/v1/internal/rules/active"
	urlOrg := ""
	if orgID != "" {
		urlOrg = strings.TrimRight(backendURL, "/") + "/api/v1/internal/orgs/" + orgID + "/rules/active"
	}

	fetch := func() {
		url := urlAll
		if urlOrg != "" && os.Getenv("RULES_SYNC_SINGLE_ORG") == "1" {
			url = urlOrg
		}
		req, err := http.NewRequest(http.MethodGet, url, nil)
		if err != nil {
			return
		}
		req.Header.Set("X-Internal-Key", apiKey)
		client := &http.Client{Timeout: 15 * time.Second}
		resp, err := client.Do(req)
		if err != nil {
			log.Printf("rules sync fetch failed: %v", err)
			return
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			body, _ := io.ReadAll(resp.Body)
			log.Printf("rules sync HTTP %d: %s", resp.StatusCode, string(body))
			return
		}
		var rows []dbRule
		if err := json.NewDecoder(resp.Body).Decode(&rows); err != nil {
			log.Printf("rules sync decode failed: %v", err)
			return
		}
		out := make([]evaluator.RuleDefinition, 0, len(rows))
		for _, row := range rows {
			if !row.IsEnabled {
				continue
			}
			def, err := toEvaluatorRule(row)
			if err != nil {
				log.Printf("skip rule %s: %v", row.ID, err)
				continue
			}
			out = append(out, def)
		}
		apply(out)
		log.Printf("synced %d active rules from backend", len(out))
	}

	fetch()
	go func() {
		t := time.NewTicker(interval)
		defer t.Stop()
		for range t.C {
			fetch()
		}
	}()
}

func toEvaluatorRule(row dbRule) (evaluator.RuleDefinition, error) {
	var def evaluator.RuleDefinition
	if err := json.Unmarshal(row.Definition, &def); err != nil {
		return def, err
	}
	def.RuleID = row.ID
	def.Name = row.Name
	def.Enabled = row.IsEnabled
	if def.RuleID == "" {
		return def, fmt.Errorf("missing rule id")
	}
        if def.CameraID == "" {
		var extra struct {
			CameraID string `json:"camera_id"`
			Bindings struct {
				CameraID string `json:"camera_id"`
			} `json:"bindings"`
		}
		_ = json.Unmarshal(row.Definition, &extra)
		if extra.CameraID != "" {
			def.CameraID = extra.CameraID
		} else if extra.Bindings.CameraID != "" {
			def.CameraID = extra.Bindings.CameraID
		}
	}
	return def, nil
}

func Env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
