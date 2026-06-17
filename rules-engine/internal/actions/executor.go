package actions

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/citevision/citevision-v2/rules-engine/internal/evaluator"
	mqttpub "github.com/citevision/citevision-v2/rules-engine/internal/mqttpub"
)

type Executor struct {
	Publisher   *mqttpub.Publisher
	BackendURL  string
	InternalKey string
	HTTP        *http.Client
}

func New(publisher *mqttpub.Publisher, backendURL, internalKey string) *Executor {
	return &Executor{
		Publisher:   publisher,
		BackendURL:  backendURL,
		InternalKey: internalKey,
		HTTP:        &http.Client{Timeout: 15 * time.Second},
	}
}

func (e *Executor) Run(orgID string, rule evaluator.RuleDefinition, payload map[string]interface{}, actions []evaluator.Action) {
	logs := []map[string]interface{}{}
	var alertActs []evaluator.Action
	for _, act := range actions {
		if act.Type == "alert" {
			alertActs = append(alertActs, act)
			continue
		}
		logs = append(logs, e.runNonAlert(orgID, rule, payload, act))
	}
	for _, act := range alertActs {
		payload["action_log"] = logs
		e.runAlert(orgID, rule, payload, act)
		logs = append(logs, map[string]interface{}{
			"type": "alert", "timestamp": time.Now().UTC().Format(time.RFC3339), "status": "executed",
		})
	}
	if len(logs) > 0 {
		payload["action_log"] = logs
	}
}

func (e *Executor) runNonAlert(orgID string, rule evaluator.RuleDefinition, payload map[string]interface{}, act evaluator.Action) map[string]interface{} {
	entry := map[string]interface{}{
		"type": act.Type, "timestamp": time.Now().UTC().Format(time.RFC3339),
	}
	switch act.Type {
	case "record":
		e.runRecord(orgID, rule, payload, act)
		entry["status"] = "executed"
	case "notify":
		if e.runNotify(orgID, rule, payload, act) {
			entry["status"] = "executed"
		} else {
			entry["status"] = "skipped"
		}
	case "webhook":
		if e.runWebhook(orgID, rule, payload, act) {
			entry["status"] = "executed"
		} else {
			entry["status"] = "skipped"
		}
	case "incident":
		e.runIncident(orgID, rule, payload, act)
		entry["status"] = "executed"
	case "counter":
		e.runCounter(orgID, rule, act)
		entry["status"] = "executed"
	case "log":
		e.runLog(orgID, rule, payload, act)
		entry["status"] = "executed"
	case "archive_auto":
		e.runArchiveAuto(orgID, rule, payload, act)
		entry["status"] = "executed"
	case "trigger_rule":
		if e.runTriggerRule(orgID, rule, payload, act) {
			entry["status"] = "executed"
		} else {
			entry["status"] = "skipped"
		}
	default:
		log.Printf("action type %q not in honest registry", act.Type)
		entry["status"] = "not_implemented"
	}
	return entry
}

func (e *Executor) enrichedMeta(orgID string, rule evaluator.RuleDefinition, payload map[string]interface{}, extra map[string]interface{}) map[string]interface{} {
	meta := map[string]interface{}{
		"topic":           "cv/events",
		"rule_id":         rule.RuleID,
		"camera_id":       payload["camera_id"],
		"payload":         payload,
		"confidence":      payload["confidence"],
		"bbox":            payload["bbox"],
		"track_id":        payload["track_id"],
		"zone_id":         payload["zone_id"],
		"line_id":         payload["line_id"],
		"plate_number":    payload["plate_number"],
		"face_label":      payload["face_label"],
		"event_type":      payload["event_type"],
		"speed_kmh":       payload["speed_kmh"],
		"direction":       payload["direction"],
		"matched_rule_id": rule.RuleID,
		"org_id":          orgID,
	}
	if ev, ok := payload["evidence"].(map[string]interface{}); ok {
		meta["evidence"] = ev
	}
	if pkg, ok := payload["package"]; ok {
		meta["package"] = pkg
	}
	if es, ok := payload["evidence_snapshot"].(map[string]interface{}); ok {
		meta["evidence_snapshot"] = es
	}
	for k, v := range extra {
		meta[k] = v
	}
	if logs, ok := payload["action_log"]; ok {
		meta["action_log"] = logs
	}
	return meta
}

func (e *Executor) runAlert(orgID string, rule evaluator.RuleDefinition, payload map[string]interface{}, act evaluator.Action) {
	severity := "medium"
	var cfg map[string]interface{}
	_ = json.Unmarshal(act.Config, &cfg)
	if s, ok := cfg["severity"].(string); ok && s != "" {
		severity = s
	}
	e.ensureEvidencePackage(orgID, rule, payload)
	evPolicy := defaultEvidencePolicy()
	if rule.Evidence != nil {
		evPolicy = rule.Evidence
	}
	if policyRequiresProof(evPolicy) && !hasEvidencePackage(payload, evPolicy) {
		log.Printf("alert suppressed: incomplete evidence for rule %s", rule.RuleID)
		return
	}
	meta := e.enrichedMeta(orgID, rule, payload, nil)
	evidence := buildEvidenceSnapshot(payload)
	meta["evidence_snapshot"] = evidence
	if e.Publisher != nil {
		e.Publisher.PublishAlert(orgID, rule.RuleID, rule.Name, "Règle déclenchée: "+rule.Name, severity, meta)
	}
}

func (e *Executor) ensureEvidencePackage(orgID string, rule evaluator.RuleDefinition, payload map[string]interface{}) {
	evPolicy := defaultEvidencePolicy()
	if rule.Evidence != nil {
		evPolicy = rule.Evidence
	}
	if hasEvidencePackage(payload, evPolicy) {
		return
	}
	cameraID, _ := payload["camera_id"].(string)
	if cameraID == "" {
		cameraID = rule.CameraID
	}
	if cameraID == "" {
		return
	}
	body, _ := json.Marshal(map[string]interface{}{
		"camera_id": cameraID,
		"event":     payload,
		"evidence":  evPolicy,
	})
	url := fmt.Sprintf("%s/internal/orgs/%s/evidence/request", e.BackendURL, orgID)
	resp := e.postInternal(url, body)
	if pkg, ok := resp["package"]; ok {
		payload["package"] = pkg
	}
	if ev, ok := resp["evidence"].(map[string]interface{}); ok {
		payload["evidence"] = ev
		if pkg, ok := ev["package"]; ok {
			payload["package"] = pkg
		}
	}
}

func hasEvidencePackage(payload map[string]interface{}, policy map[string]interface{}) bool {
	pkg := extractPackage(payload)
	if pkg == nil {
		return false
	}
	needClip := true
	if policy != nil {
		if en, ok := policy["enabled"].(bool); ok && !en {
			return true
		}
		if cs, ok := policy["clip_seconds"].(float64); ok {
			needClip = cs > 0
		}
	}
	if needClip {
		clip, _ := pkg["clip"].(map[string]interface{})
		if clip == nil || (clip["url"] == nil && clip["asset_id"] == nil) {
			return false
		}
	}
	images, _ := pkg["images"].([]interface{})
	roles := map[string]bool{}
	for _, im := range images {
		m, _ := im.(map[string]interface{})
		if m == nil {
			continue
		}
		role, _ := m["role"].(string)
		if (m["url"] != nil || m["asset_id"] != nil) && role != "" {
			roles[role] = true
		}
	}
	required := []string{"scene", "subject"}
	if policy != nil {
		if imgs, ok := policy["images"].([]interface{}); ok && len(imgs) > 0 {
			required = required[:0]
			for _, im := range imgs {
				m, _ := im.(map[string]interface{})
				if m == nil {
					continue
				}
				if role, ok := m["role"].(string); ok && role != "" {
					required = append(required, role)
				}
			}
		}
	}
	for _, r := range required {
		if !roles[r] {
			return false
		}
	}
	return true
}

func policyRequiresProof(policy map[string]interface{}) bool {
	if policy == nil {
		return true
	}
	if en, ok := policy["enabled"].(bool); ok {
		return en
	}
	return true
}

func extractPackage(payload map[string]interface{}) map[string]interface{} {
	if pkg, ok := payload["package"].(map[string]interface{}); ok && pkg != nil {
		return pkg
	}
	if ev, ok := payload["evidence"].(map[string]interface{}); ok {
		if pkg, ok := ev["package"].(map[string]interface{}); ok {
			return pkg
		}
	}
	return nil
}

func defaultEvidencePolicy() map[string]interface{} {
	return map[string]interface{}{
		"enabled":      true,
		"clip_seconds": 6,
		"images": []map[string]interface{}{
			{"role": "scene", "label": "Vue d'ensemble", "crop": "full"},
			{"role": "subject", "label": "Cible détectée", "crop": "bbox", "padding_pct": 10, "zoom": 1.0},
		},
	}
}

func (e *Executor) runRecord(orgID string, rule evaluator.RuleDefinition, payload map[string]interface{}, act evaluator.Action) {
	duration := 30
	var cfg map[string]interface{}
	_ = json.Unmarshal(act.Config, &cfg)
	if d, ok := cfg["duration_sec"].(float64); ok && d > 0 {
		duration = int(d)
	}
	if d, ok := cfg["duration_seconds"].(float64); ok && d > 0 {
		duration = int(d)
	}
	cameraID, _ := payload["camera_id"].(string)
	if cameraID == "" {
		cameraID = rule.CameraID
	}
	body, _ := json.Marshal(map[string]interface{}{
		"camera_id":       cameraID,
		"duration_sec":    duration,
		"rule_id":         rule.RuleID,
		"trigger_payload": payload,
	})
	url := fmt.Sprintf("%s/internal/orgs/%s/record/clip", e.BackendURL, orgID)
	resp := e.postInternal(url, body)
	if path, ok := resp["clip_path"].(string); ok && path != "" {
		payload["clip_path"] = path
	} else if path, ok := resp["path"].(string); ok && path != "" {
		payload["clip_path"] = path
	}
}

func (e *Executor) orgNotificationDefaults(orgID string) (email, webhook string) {
	url := fmt.Sprintf("%s/internal/orgs/%s/notification-defaults", e.BackendURL, orgID)
	out := e.getInternal(url)
	email, _ = out["default_email_to"].(string)
	webhook, _ = out["default_webhook_url"].(string)
	return email, webhook
}

func (e *Executor) runNotify(orgID string, rule evaluator.RuleDefinition, payload map[string]interface{}, act evaluator.Action) bool {
	var cfg map[string]interface{}
	_ = json.Unmarshal(act.Config, &cfg)
	channel, _ := cfg["channel"].(string)
	if channel != "" && channel != "email" {
		return false
	}
	to, _ := cfg["to"].(string)
	if to == "" {
		defEmail, _ := e.orgNotificationDefaults(orgID)
		to = defEmail
	}
	if to == "" {
		to = os.Getenv("ALERT_EMAIL_TO")
	}
	if to == "" {
		return false
	}
	evSnap := buildEvidenceSnapshot(payload)
	msg := fmt.Sprintf("Règle « %s » déclenchée.\nCaméra: %v\nÉvénement: %v\n", rule.Name, payload["camera_id"], payload["event_type"])
	msg += formatEvidenceLinksForEmail(evSnap)
	body, _ := json.Marshal(map[string]interface{}{
		"to":      to,
		"subject": "Alerte CitéVision — " + rule.Name,
		"message": msg,
	})
	url := fmt.Sprintf("%s/internal/orgs/%s/notify/email", e.BackendURL, orgID)
	e.postInternal(url, body)
	return true
}

func formatEvidenceLinksForEmail(evSnap map[string]interface{}) string {
	if evSnap == nil {
		return ""
	}
	pkg, _ := evSnap["package"].(map[string]interface{})
	if pkg == nil {
		return ""
	}
	var b strings.Builder
	b.WriteString("\nPreuves :\n")
	if clip, ok := pkg["clip"].(map[string]interface{}); ok {
		if u, ok := clip["url"].(string); ok && u != "" {
			fmt.Fprintf(&b, "- Clip : %s\n", u)
		}
	}
	if imgs, ok := pkg["images"].([]interface{}); ok {
		for _, im := range imgs {
			m, _ := im.(map[string]interface{})
			if u, ok := m["url"].(string); ok && u != "" {
				fmt.Fprintf(&b, "- Image : %s\n", u)
			}
		}
	}
	return b.String()
}

func (e *Executor) runWebhook(orgID string, rule evaluator.RuleDefinition, payload map[string]interface{}, act evaluator.Action) bool {
	var cfg map[string]interface{}
	_ = json.Unmarshal(act.Config, &cfg)
	url, _ := cfg["url"].(string)
	if url == "" {
		_, defWebhook := e.orgNotificationDefaults(orgID)
		url = defWebhook
	}
	if url == "" {
		url = os.Getenv("WEBHOOK_LOCAL_URL")
	}
	if url == "" {
		return false
	}
	evSnap := buildEvidenceSnapshot(payload)
	webhookPayload := map[string]interface{}{
		"org_id":            orgID,
		"rule_id":           rule.RuleID,
		"rule_name":         rule.Name,
		"timestamp":         time.Now().UTC().Format(time.RFC3339),
		"event":             payload,
		"evidence_snapshot": evSnap,
		"camera_id":         payload["camera_id"],
		"zone_id":           payload["zone_id"],
		"class_name":        payload["class_name"],
		"event_type":        payload["event_type"],
	}
	if preset, ok := cfg["preset"].(string); ok && preset != "" {
		webhookPayload["integration_preset"] = preset
	}
	body, _ := json.Marshal(map[string]interface{}{
		"url":     url,
		"payload": webhookPayload,
	})
	ep := fmt.Sprintf("%s/internal/orgs/%s/webhook", e.BackendURL, orgID)
	e.postInternal(ep, body)
	return true
}

func (e *Executor) runIncident(orgID string, rule evaluator.RuleDefinition, payload map[string]interface{}, act evaluator.Action) {
	severity := "high"
	var cfg map[string]interface{}
	_ = json.Unmarshal(act.Config, &cfg)
	if s, ok := cfg["severity"].(string); ok && s != "" {
		severity = s
	}
	body, _ := json.Marshal(map[string]interface{}{
		"title":       "Incident — " + rule.Name,
		"description": fmt.Sprintf("Déclenché par règle %s sur caméra %v", rule.Name, payload["camera_id"]),
		"severity":    severity,
		"metadata":    payload,
	})
	url := fmt.Sprintf("%s/internal/orgs/%s/incidents", e.BackendURL, orgID)
	e.postInternal(url, body)
}

func (e *Executor) runCounter(orgID string, rule evaluator.RuleDefinition, act evaluator.Action) {
	delta := 1
	var cfg map[string]interface{}
	_ = json.Unmarshal(act.Config, &cfg)
	if d, ok := cfg["delta"].(float64); ok && d != 0 {
		delta = int(d)
	}
	body, _ := json.Marshal(map[string]interface{}{
		"rule_id": rule.RuleID,
		"delta":   delta,
	})
	url := fmt.Sprintf("%s/internal/orgs/%s/rules/counter", e.BackendURL, orgID)
	e.postInternal(url, body)
}

func (e *Executor) runLog(orgID string, rule evaluator.RuleDefinition, payload map[string]interface{}, act evaluator.Action) {
	path := os.Getenv("ACTION_LOG_PATH")
	if path == "" {
		path = filepath.Join(os.TempDir(), "citevision-actions.log")
	}
	line, _ := json.Marshal(map[string]interface{}{
		"ts":      time.Now().UTC().Format(time.RFC3339),
		"org_id":  orgID,
		"rule_id": rule.RuleID,
		"event":   payload,
	})
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		log.Printf("action log file: %v", err)
		return
	}
	defer f.Close()
	_, _ = f.Write(append(line, '\n'))
}

func (e *Executor) runTriggerRule(orgID string, rule evaluator.RuleDefinition, payload map[string]interface{}, act evaluator.Action) bool {
	var cfg struct {
		RuleID string `json:"rule_id"`
	}
	_ = json.Unmarshal(act.Config, &cfg)
	target := strings.TrimSpace(cfg.RuleID)
	if target == "" || target == rule.RuleID {
		return false
	}
	if e.Publisher != nil {
		e.Publisher.PublishRuleTrigger(orgID, target, payload)
	}
	return true
}

func (e *Executor) runArchiveAuto(orgID string, rule evaluator.RuleDefinition, payload map[string]interface{}, act evaluator.Action) {
	afterMin := 5
	var cfg map[string]interface{}
	_ = json.Unmarshal(act.Config, &cfg)
	if m, ok := cfg["after_minutes"].(float64); ok && m > 0 {
		afterMin = int(m)
	}
	evSnap := buildEvidenceSnapshot(payload)
	body, _ := json.Marshal(map[string]interface{}{
		"rule_id":           rule.RuleID,
		"older_than_min":    afterMin,
		"comment":           fmt.Sprintf("Archivage auto après %d min (règle %s)", afterMin, rule.Name),
		"evidence_snapshot": evSnap,
	})
	url := fmt.Sprintf("%s/internal/orgs/%s/alerts/archive-stale", e.BackendURL, orgID)
	e.postInternal(url, body)
}

func buildEvidenceSnapshot(payload map[string]interface{}) map[string]interface{} {
	out := map[string]interface{}{}
	for _, k := range []string{"bbox", "confidence", "plate_number", "face_label", "event_type", "clip_path",
		"zone_id", "line_id", "track_id", "class_name", "camera_id", "package"} {
		if v, ok := payload[k]; ok && v != nil {
			out[k] = v
		}
	}
	if ev, ok := payload["evidence"].(map[string]interface{}); ok {
		out["evidence"] = ev
		if pkg, ok := ev["package"]; ok {
			out["package"] = pkg
		}
	}
	if es, ok := payload["evidence_snapshot"].(map[string]interface{}); ok {
		for k, v := range es {
			out[k] = v
		}
	}
	return out
}

func (e *Executor) postInternal(url string, body []byte) map[string]interface{} {
	out := map[string]interface{}{}
	if e.BackendURL == "" {
		return out
	}
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return out
	}
	req.Header.Set("Content-Type", "application/json")
	if e.InternalKey != "" {
		req.Header.Set("X-Internal-Key", e.InternalKey)
	}
	resp, err := e.HTTP.Do(req)
	if err != nil {
		log.Printf("internal action failed: %v", err)
		return out
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		log.Printf("internal action HTTP %d for %s", resp.StatusCode, url)
		return out
	}
	_ = json.Unmarshal(respBody, &out)
	return out
}

func (e *Executor) getInternal(url string) map[string]interface{} {
	out := map[string]interface{}{}
	if e.BackendURL == "" {
		return out
	}
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return out
	}
	if e.InternalKey != "" {
		req.Header.Set("X-Internal-Key", e.InternalKey)
	}
	resp, err := e.HTTP.Do(req)
	if err != nil {
		return out
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return out
	}
	_ = json.Unmarshal(respBody, &out)
	return out
}
