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
	mu      sync.Mutex
}

func New(broker string, port int, handler Handler) *Subscriber {
	opts := mqtt.NewClientOptions().
		AddBroker(broker).
		SetClientID("citevision-rules-engine")
	return &Subscriber{
		client:  mqtt.NewClient(opts),
		handler: handler,
	}
}

func (s *Subscriber) Connect() error {
	token := s.client.Connect()
	token.Wait()
	return token.Error()
}

func (s *Subscriber) Subscribe(topics ...string) error {
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
