package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/citevision/citevision-v2/rules-engine/internal/dedup"
	"github.com/citevision/citevision-v2/rules-engine/internal/evaluator"
	mqttsub "github.com/citevision/citevision-v2/rules-engine/internal/mqtt"
)

func main() {
	host := getenv("RULES_ENGINE_HOST", "0.0.0.0")
	port := getenv("RULES_ENGINE_PORT", "8010")
	mqttHost := getenv("MQTT_HOST", "localhost")
	mqttPort := getenv("MQTT_PORT", "1884")
	dedupTTL := 60

	rules := loadRulesFromEnv()
	cache := dedup.NewCache(time.Duration(dedupTTL) * time.Second)

	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ok","service":"citevision-rules-engine"}`))
	})

	go func() {
		addr := fmt.Sprintf("%s:%s", host, port)
		log.Printf("Rules engine HTTP listening on %s", addr)
		if err := http.ListenAndServe(addr, mux); err != nil {
			log.Fatal(err)
		}
	}()

	broker := fmt.Sprintf("tcp://%s:%s", mqttHost, mqttPort)
	sub := mqttsub.New(broker, 0, func(topic string, payload map[string]interface{}) {
		now := time.Now()
		for _, rule := range rules {
			if rule.CameraID != "" {
				if cam, ok := payload["camera_id"].(string); ok && cam != rule.CameraID {
					continue
				}
			}
			ok, actions := evaluator.Evaluate(rule, payload, now)
			if !ok {
				continue
			}
			key := evaluator.DedupKey(rule, payload)
			if cache.IsDuplicate(key, now) {
				continue
			}
			log.Printf("rule %s matched on %s actions=%d", rule.RuleID, topic, len(actions))
		}
	})

	if err := sub.Connect(); err != nil {
		log.Printf("MQTT connect failed (will retry in background): %v", err)
	} else {
		if err := sub.Subscribe("cv/events/#", "cv/detections/#"); err != nil {
			log.Printf("MQTT subscribe failed: %v", err)
		} else {
			log.Printf("Subscribed to cv/events/# and cv/detections/# on %s", broker)
		}
	}

	select {}
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func loadRulesFromEnv() []evaluator.RuleDefinition {
	path := os.Getenv("RULES_CATALOG_PATH")
	if path == "" {
		path = "../shared/rule-catalog/intrusion-loitering-line-theft.json"
	}
	data, err := os.ReadFile(path)
	if err != nil {
		log.Printf("no rules catalog at %s: %v", path, err)
		return nil
	}
	var templates []struct {
		ID         string          `json:"id"`
		Name       string          `json:"name"`
		Definition json.RawMessage `json:"definition"`
	}
	if err := json.Unmarshal(data, &templates); err != nil {
		log.Printf("invalid rules catalog: %v", err)
		return nil
	}
	rules := make([]evaluator.RuleDefinition, 0, len(templates))
	for _, tpl := range templates {
		var def evaluator.RuleDefinition
		if err := json.Unmarshal(tpl.Definition, &def); err != nil {
			continue
		}
		def.RuleID = tpl.ID
		def.Name = tpl.Name
		def.Enabled = true
		rules = append(rules, def)
	}
	log.Printf("Loaded %d rules from catalog", len(rules))
	return rules
}

func init() {
	_ = strings.TrimSpace
}
