package rules

import (
	"encoding/json"
	"fmt"
	"strings"
)

var spatialTemplatesRequiringClass = map[string]bool{
	"tpl-zone-presence":     true,
	"tpl-zone-enter":        true,
	"tpl-zone-exit":         true,
	"tpl-line-cross":        true,
	"tpl-line-cross-bidir":  true,
	"tpl-loitering":         true,
	"tpl-intrusion-zone":    true,
}

func validateSpatialClassFilter(def map[string]interface{}) error {
	bindings, _ := def["bindings"].(map[string]interface{})
	if bindings == nil {
		return nil
	}
	tpl, _ := bindings["template_id"].(string)
	if tpl == "" || !spatialTemplatesRequiringClass[tpl] {
		return nil
	}
	if cf, ok := bindings["class_filter"].(string); ok && strings.TrimSpace(cf) != "" {
		return nil
	}
	if hasMatchesClassCondition(def) {
		return nil
	}
	return fmt.Errorf("class_filter is required for spatial rule template %q", tpl)
}

func hasMatchesClassCondition(def map[string]interface{}) bool {
	cond, _ := def["condition"].(map[string]interface{})
	return walkHasMatchesClass(cond)
}

func walkHasMatchesClass(node map[string]interface{}) bool {
	if node == nil {
		return false
	}
	if op, _ := node["op"].(string); strings.EqualFold(op, "matches_class") {
		if v := fmt.Sprint(node["value"]); strings.TrimSpace(v) != "" {
			return true
		}
	}
	children, _ := node["children"].([]interface{})
	for _, c := range children {
		if cm, ok := c.(map[string]interface{}); ok && walkHasMatchesClass(cm) {
			return true
		}
	}
	return false
}

func validateDefinitionMap(raw json.RawMessage) error {
	var def map[string]interface{}
	if err := json.Unmarshal(raw, &def); err != nil {
		return fmt.Errorf("invalid rule definition: %w", err)
	}
	return validateSpatialClassFilter(def)
}
