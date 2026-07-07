package mqttsub

import (
	"encoding/json"
	"log"
	"sync"

	mqtt "github.com/eclipse/paho.mqtt.golang"
)

type Handler func(topic string, payload map[string]interface{})

type Subscriber struct {
	client  mqtt.Client
	handler Handler
	topics  []string
	mu      sync.Mutex
}

func New(broker string, port int, handler Handler) *Subscriber {
	s := &Subscriber{handler: handler}
	opts := mqtt.NewClientOptions().
		AddBroker(broker).
		SetClientID("citevision-rules-engine").
		SetAutoReconnect(true).
		SetResumeSubs(true).
		SetOnConnectHandler(func(c mqtt.Client) {
			s.mu.Lock()
			defer s.mu.Unlock()
			for _, topic := range s.topics {
				topic := topic
				c.Subscribe(topic, 1, func(_ mqtt.Client, msg mqtt.Message) { //nolint:errcheck
					var payload map[string]interface{}
					if err := json.Unmarshal(msg.Payload(), &payload); err != nil {
						log.Printf("invalid payload on %s: %v", msg.Topic(), err)
						return
					}
					s.handler(msg.Topic(), payload)
				})
			}
			if len(s.topics) > 0 {
				log.Printf("MQTT re-subscribed to %v after reconnect", s.topics)
			}
		}).
		SetConnectionLostHandler(func(_ mqtt.Client, err error) {
			log.Printf("MQTT connection lost: %v — will auto-reconnect", err)
		})
	s.client = mqtt.NewClient(opts)
	return s
}

func (s *Subscriber) RegisterTopics(topics ...string) {
	s.mu.Lock()
	s.topics = append(s.topics, topics...)
	s.mu.Unlock()
}

func (s *Subscriber) Connect() error {
	token := s.client.Connect()
	token.Wait()
	return token.Error()
}

func (s *Subscriber) Subscribe(topics ...string) error {
	s.RegisterTopics(topics...)
	for _, topic := range topics {
		topic := topic
		token := s.client.Subscribe(topic, 1, func(_ mqtt.Client, msg mqtt.Message) {
			var payload map[string]interface{}
			if err := json.Unmarshal(msg.Payload(), &payload); err != nil {
				log.Printf("invalid payload on %s: %v", msg.Topic(), err)
				return
			}
			s.handler(msg.Topic(), payload)
		})
		token.Wait()
		if err := token.Error(); err != nil {
			return err
		}
	}
	return nil
}

func (s *Subscriber) Disconnect() {
	s.client.Disconnect(250)
}
