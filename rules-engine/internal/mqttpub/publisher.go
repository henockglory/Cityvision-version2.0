package mqttpub

import (
	"encoding/json"
	"log"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
)

type Publisher struct {
	client mqtt.Client
}

func New(broker string) *Publisher {
	opts := mqtt.NewClientOptions().
		AddBroker(broker).
		SetClientID("citevision-rules-publisher").
		SetAutoReconnect(true)
	client := mqtt.NewClient(opts)
	token := client.Connect()
	token.Wait()
	if err := token.Error(); err != nil {
		log.Printf("rules mqtt publisher connect failed: %v", err)
		return &Publisher{client: client}
	}
	return &Publisher{client: client}
}

func (p *Publisher) PublishMatchedEvent(orgID, ruleID string, payload map[string]interface{}) {
	if p == nil || p.client == nil || !p.client.IsConnected() {
		return
	}
	enriched := make(map[string]interface{}, len(payload)+2)
	for k, v := range payload {
		enriched[k] = v
	}
	enriched["matched_rule_id"] = ruleID
	enriched["org_id"] = orgID
	b, _ := json.Marshal(enriched)
	topic := "cv/events/" + orgID
	token := p.client.Publish(topic, 1, false, b)
	token.Wait()
}

func (p *Publisher) PublishRuleTrigger(orgID, targetRuleID string, payload map[string]interface{}) {
	if p == nil || p.client == nil || !p.client.IsConnected() {
		return
	}
	enriched := make(map[string]interface{}, len(payload)+3)
	for k, v := range payload {
		enriched[k] = v
	}
	enriched["org_id"] = orgID
	enriched["trigger_rule_id"] = targetRuleID
	enriched["event_type"] = "rule_trigger"
	enriched["event"] = "rule_trigger"
	b, _ := json.Marshal(enriched)
	topic := "cv/rules/trigger/" + orgID
	token := p.client.Publish(topic, 1, false, b)
	token.Wait()
}

func (p *Publisher) PublishAlert(orgID, ruleID, title, message, severity string, metadata map[string]interface{}) {
	if p == nil || p.client == nil || !p.client.IsConnected() {
		return
	}
	payload := map[string]interface{}{
		"org_id":   orgID,
		"rule_id":  ruleID,
		"title":    title,
		"message":  message,
		"severity": severity,
		"metadata": metadata,
		"ts":       time.Now().UTC().Format(time.RFC3339),
	}
	b, _ := json.Marshal(payload)
	topic := "cv/alerts/" + orgID
	token := p.client.Publish(topic, 1, false, b)
	token.Wait()
}
