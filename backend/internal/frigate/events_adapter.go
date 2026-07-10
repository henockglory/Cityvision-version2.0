package frigate

import (
	"context"
	"encoding/json"
	"log/slog"
	"os"
	"strings"

	mqtt "github.com/eclipse/paho.mqtt.golang"
)

// EventAdapter subscribes to Frigate MQTT events (debug/presence only — off by default).
// Never emits speeding or other business events; FRIGATE_EVENTS=0 has zero impact.
type EventAdapter struct {
	cfg    Config
	broker string
	client mqtt.Client
	log    *slog.Logger
}

func NewEventAdapter(cfg Config, broker string, log *slog.Logger) *EventAdapter {
	if log == nil {
		log = slog.Default()
	}
	if broker == "" {
		host := envOr("MQTT_HOST", "127.0.0.1")
		port := envOr("MQTT_PORT", "1884")
		broker = "tcp://" + host + ":" + port
	}
	return &EventAdapter{cfg: cfg, broker: broker, log: log}
}

func (a *EventAdapter) Start(ctx context.Context) {
	if !a.cfg.Enabled || !a.cfg.Events {
		return
	}
	opts := mqtt.NewClientOptions().
		AddBroker(a.broker).
		SetClientID("citevision-frigate-events").
		SetAutoReconnect(true)
	opts.SetDefaultPublishHandler(nil)
	a.client = mqtt.NewClient(opts)
	if token := a.client.Connect(); token.Wait() && token.Error() != nil {
		a.log.Warn("frigate event adapter connect failed", "error", token.Error())
		return
	}
	if token := a.client.Subscribe("frigate/events", 0, a.handleMessage); token.Wait() && token.Error() != nil {
		a.log.Warn("frigate mqtt subscribe failed", "error", token.Error())
	}
	a.log.Info("frigate event adapter started (debug only)")
	go func() {
		<-ctx.Done()
		a.client.Disconnect(250)
	}()
}

func (a *EventAdapter) handleMessage(_ mqtt.Client, msg mqtt.Message) {
	var payload map[string]interface{}
	if err := json.Unmarshal(msg.Payload(), &payload); err != nil {
		return
	}
	after, _ := payload["after"].(map[string]interface{})
	if after == nil {
		return
	}
	label, _ := after["label"].(string)
	cam, _ := after["camera"].(string)
	if strings.Contains(strings.ToLower(label), "speed") {
		return
	}
	a.log.Debug("frigate mqtt event", "camera", cam, "label", label)
}

func envOr(key, def string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return def
}
