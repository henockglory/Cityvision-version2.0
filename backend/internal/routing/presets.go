package routing

import "fmt"

// Preset identifiers understood by the routing dispatcher.
const (
	PresetGeneric = ""
	PresetN8N     = "n8n"
	PresetMake    = "make"
	PresetZapier  = "zapier"
	PresetSlack   = "slack"
	PresetTeams   = "teams"
	PresetDiscord = "discord"
)

// SupportedPresets is the catalog exposed to the UI.
var SupportedPresets = []string{
	PresetN8N, PresetMake, PresetZapier, PresetSlack, PresetTeams, PresetDiscord,
}

// transformForPreset adapts the canonical alert payload to a destination's
// expected schema. The second return value reports whether the CloudEvents
// envelope should still be applied (true for automation platforms that consume
// generic JSON; false for chat webhooks that require their own body shape).
func transformForPreset(preset string, p map[string]interface{}) (map[string]interface{}, bool) {
	switch preset {
	case PresetSlack:
		return slackBody(p), false
	case PresetTeams:
		return teamsBody(p), false
	case PresetDiscord:
		return discordBody(p), false
	case PresetN8N, PresetMake, PresetZapier, PresetGeneric:
		fallthrough
	default:
		// Automation platforms ingest the raw payload; keep CloudEvents.
		return p, true
	}
}

func summaryLine(p map[string]interface{}) string {
	title, _ := p["title"].(string)
	sev, _ := p["severity"].(string)
	rule, _ := p["rule_name"].(string)
	if title == "" {
		title = "CiteVision alert"
	}
	line := fmt.Sprintf("[%s] %s", sev, title)
	if rule != "" {
		line += " — " + rule
	}
	return line
}

func detailFields(p map[string]interface{}) map[string]string {
	out := map[string]string{}
	for _, k := range []string{"plate_number", "face_label", "event_type", "camera_id"} {
		if v, ok := p[k].(string); ok && v != "" {
			out[k] = v
		}
	}
	return out
}

func slackBody(p map[string]interface{}) map[string]interface{} {
	text := "*CiteVision* " + summaryLine(p)
	fields := []map[string]interface{}{}
	for k, v := range detailFields(p) {
		fields = append(fields, map[string]interface{}{
			"type": "mrkdwn", "text": fmt.Sprintf("*%s:*\n%s", k, v),
		})
	}
	blocks := []map[string]interface{}{
		{"type": "section", "text": map[string]interface{}{"type": "mrkdwn", "text": text}},
	}
	if len(fields) > 0 {
		blocks = append(blocks, map[string]interface{}{"type": "section", "fields": fields})
	}
	return map[string]interface{}{"text": text, "blocks": blocks}
}

func discordBody(p map[string]interface{}) map[string]interface{} {
	embedFields := []map[string]interface{}{}
	for k, v := range detailFields(p) {
		embedFields = append(embedFields, map[string]interface{}{
			"name": k, "value": v, "inline": true,
		})
	}
	title, _ := p["title"].(string)
	return map[string]interface{}{
		"content": "**CiteVision** " + summaryLine(p),
		"embeds": []map[string]interface{}{{
			"title":  title,
			"color":  severityColor(p),
			"fields": embedFields,
		}},
	}
}

func teamsBody(p map[string]interface{}) map[string]interface{} {
	facts := []map[string]interface{}{}
	for k, v := range detailFields(p) {
		facts = append(facts, map[string]interface{}{"name": k, "value": v})
	}
	title, _ := p["title"].(string)
	return map[string]interface{}{
		"@type":      "MessageCard",
		"@context":   "http://schema.org/extensions",
		"themeColor": fmt.Sprintf("%06X", severityColor(p)),
		"summary":    "CiteVision alert",
		"title":      "CiteVision — " + title,
		"sections": []map[string]interface{}{{
			"activitySubtitle": summaryLine(p),
			"facts":            facts,
		}},
	}
}

func severityColor(p map[string]interface{}) int {
	sev, _ := p["severity"].(string)
	switch sev {
	case "critical", "CRITICAL":
		return 0xE01E37 // red
	case "high", "HIGH":
		return 0xF59E0B // amber
	case "medium", "MEDIUM":
		return 0x3B82F6 // blue
	default:
		return 0x6B7280 // gray
	}
}
