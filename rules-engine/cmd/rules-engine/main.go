package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"sort"
	"sync"
	"time"

	"github.com/citevision/citevision-v2/rules-engine/internal/actions"
	"github.com/citevision/citevision-v2/rules-engine/internal/dedup"
	"github.com/citevision/citevision-v2/rules-engine/internal/evaluator"
	mqttsub "github.com/citevision/citevision-v2/rules-engine/internal/mqtt"
	mqttpub "github.com/citevision/citevision-v2/rules-engine/internal/mqttpub"
	"github.com/citevision/citevision-v2/rules-engine/internal/syncrules"
)

type ruleMatch struct {
	rule    evaluator.RuleDefinition
	actions []evaluator.Action
}

func main() {
	host := getenv("RULES_ENGINE_HOST", "0.0.0.0")
	port := getenv("RULES_ENGINE_PORT", "8010")
	mqttHost := getenv("MQTT_HOST", "localhost")
	mqttPort := getenv("MQTT_PORT", "1884")
	dedupTTL := 60

	var rulesMu sync.RWMutex
	activeRules := loadRulesFromEnv()

	orgID := os.Getenv("DEFAULT_ORG_ID")
	backendURL := syncrules.Env("BACKEND_API_URL", "http://localhost:8081")
	apiKey := os.Getenv("INTERNAL_API_KEY")
	syncInterval := 30 * time.Second

	syncrules.PollActiveRules(orgID, backendURL, apiKey, syncInterval, func(rules []evaluator.RuleDefinition) {
		rulesMu.Lock()
		activeRules = rules
		rulesMu.Unlock()
	})

	cache := dedup.NewCache(time.Duration(dedupTTL) * time.Second)
	seqStore := evaluator.NewSequenceStoreFromEnv()
	broker := fmt.Sprintf("tcp://%s:%s", mqttHost, mqttPort)
	publisher := mqttpub.New(broker)
	executor := actions.New(publisher, backendURL, apiKey)
	defaultOrg := orgID

	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		rulesMu.RLock()
		n := len(activeRules)
		rulesMu.RUnlock()
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(fmt.Sprintf(`{"status":"ok","service":"citevision-rules-engine","active_rules":%d}`, n)))
	})

	go func() {
		addr := fmt.Sprintf("%s:%s", host, port)
		log.Printf("Rules engine HTTP listening on %s", addr)
		if err := http.ListenAndServe(addr, mux); err != nil {
			log.Fatal(err)
		}
	}()

	handleEvent := func(topic string, payload map[string]interface{}) {
		now := time.Now()
		rulesMu.RLock()
		rules := append([]evaluator.RuleDefinition(nil), activeRules...)
		rulesMu.RUnlock()

		sort.Slice(rules, func(i, j int) bool {
			return rules[i].Priority > rules[j].Priority
		})

		var matches []ruleMatch
		for _, rule := range rules {
			if rule.CameraID != "" {
				if cam, ok := payload["camera_id"].(string); ok && cam != rule.CameraID {
					continue
				}
			}
			if triggerID, ok := payload["trigger_rule_id"].(string); ok && triggerID != "" {
				if rule.RuleID != triggerID {
					continue
				}
			}
			ok, ruleActions := evaluator.Evaluate(rule, payload, now, seqStore)
			if !ok {
				continue
			}
			key := evaluator.DedupKey(rule, payload)
			if cache.IsDuplicate(key, now) {
				continue
			}
			matches = append(matches, ruleMatch{rule: rule, actions: ruleActions})
		}

		if len(matches) == 0 {
			return
		}

		maxPriority := matches[0].rule.Priority
		suppressFloor := 0
		for _, m := range matches {
			if m.rule.Priority > maxPriority {
				maxPriority = m.rule.Priority
			}
		}
		for _, m := range matches {
			if m.rule.SuppressLower && m.rule.Priority == maxPriority {
				suppressFloor = maxPriority
				break
			}
		}

		for _, m := range matches {
			if suppressFloor > 0 && m.rule.Priority < suppressFloor {
				continue
			}
			log.Printf("rule %s matched on %s actions=%d", m.rule.RuleID, topic, len(m.actions))

			alertOrg := defaultOrg
			if o, ok := payload["org_id"].(string); ok && o != "" {
				alertOrg = o
			}
			if alertOrg == "" {
				continue
			}
			publisher.PublishMatchedEvent(alertOrg, m.rule.RuleID, payload)
			actionsToRun := m.actions
			if len(actionsToRun) == 0 {
				actionsToRun = []evaluator.Action{{Type: "alert", Config: []byte(`{"severity":"medium"}`)}}
			}
			executor.Run(alertOrg, m.rule, payload, actionsToRun)
		}
	}

	sub := mqttsub.New(broker, 0, handleEvent)

	if err := sub.Connect(); err != nil {
		log.Printf("MQTT connect failed (will retry in background): %v", err)
	} else {
		if err := sub.Subscribe("cv/events/#", "cv/detections/#", "cv/rules/trigger/#"); err != nil {
			log.Printf("MQTT subscribe failed: %v", err)
		} else {
			log.Printf("Subscribed to cv/events/#, cv/detections/#, cv/rules/trigger/# on %s", broker)
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
	return nil
}
