package mqttsub

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"sync"
	"sync/atomic"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
)

type Handler func(topic string, payload map[string]interface{})

// Stats is a snapshot of MQTT liveness for /health and watchdogs.
type Stats struct {
	Connected         bool  `json:"mqtt_connected"`
	MessagesTotal     int64 `json:"mqtt_messages_total"`
	LastMsgUnix       int64 `json:"last_mqtt_msg_unix"`
	LastMsgAgeSec     int64 `json:"last_mqtt_msg_age_sec"`
	MatchesTotal      int64 `json:"matches_total"`
	LastMatchUnix     int64 `json:"last_match_unix"`
	LastMatchAgeSec   int64 `json:"last_match_age_sec"`
}

type Subscriber struct {
	client  mqtt.Client
	handler Handler
	topics  []string
	mu      sync.Mutex

	connected     atomic.Bool
	messagesTotal atomic.Int64
	lastMsgUnix   atomic.Int64
	matchesTotal  atomic.Int64
	lastMatchUnix atomic.Int64
}

func New(broker string, _ int, handler Handler) *Subscriber {
	s := &Subscriber{handler: handler}
	clientID := fmt.Sprintf("citevision-rules-engine-%d", os.Getpid())
	opts := mqtt.NewClientOptions().
		AddBroker(broker).
		SetClientID(clientID).
		SetAutoReconnect(true).
		SetConnectRetry(true).
		SetConnectRetryInterval(2 * time.Second).
		SetKeepAlive(30 * time.Second).
		SetPingTimeout(10 * time.Second).
		SetResumeSubs(true).
		SetOnConnectHandler(func(c mqtt.Client) {
			s.connected.Store(true)
			s.mu.Lock()
			topics := append([]string(nil), s.topics...)
			s.mu.Unlock()
			for _, topic := range topics {
				topic := topic
				token := c.Subscribe(topic, 1, s.messageHandler)
				token.Wait()
				if err := token.Error(); err != nil {
					log.Printf("MQTT subscribe failed topic=%s: %v", topic, err)
				}
			}
			if len(topics) > 0 {
				log.Printf("MQTT re-subscribed to %v after reconnect (client=%s)", topics, clientID)
			}
		}).
		SetConnectionLostHandler(func(_ mqtt.Client, err error) {
			s.connected.Store(false)
			log.Printf("MQTT connection lost: %v — will auto-reconnect", err)
		})
	s.client = mqtt.NewClient(opts)
	return s
}

func (s *Subscriber) messageHandler(_ mqtt.Client, msg mqtt.Message) {
	s.messagesTotal.Add(1)
	s.lastMsgUnix.Store(time.Now().Unix())
	var payload map[string]interface{}
	if err := json.Unmarshal(msg.Payload(), &payload); err != nil {
		log.Printf("invalid payload on %s: %v", msg.Topic(), err)
		return
	}
	if s.handler != nil {
		s.handler(msg.Topic(), payload)
	}
}

func (s *Subscriber) RegisterTopics(topics ...string) {
	s.mu.Lock()
	s.topics = append(s.topics, topics...)
	s.mu.Unlock()
}

func (s *Subscriber) Connect() error {
	token := s.client.Connect()
	token.Wait()
	if err := token.Error(); err != nil {
		s.connected.Store(false)
		return err
	}
	s.connected.Store(true)
	return nil
}

func (s *Subscriber) Subscribe(topics ...string) error {
	s.RegisterTopics(topics...)
	for _, topic := range topics {
		topic := topic
		token := s.client.Subscribe(topic, 1, s.messageHandler)
		token.Wait()
		if err := token.Error(); err != nil {
			return err
		}
	}
	return nil
}

func (s *Subscriber) Disconnect() {
	s.connected.Store(false)
	s.client.Disconnect(250)
}

// RecordMatch increments match counters when a rule fires (alert path).
func (s *Subscriber) RecordMatch() {
	s.matchesTotal.Add(1)
	s.lastMatchUnix.Store(time.Now().Unix())
}

// Snapshot returns MQTT + match liveness for /health.
func (s *Subscriber) Snapshot() Stats {
	now := time.Now().Unix()
	lastMsg := s.lastMsgUnix.Load()
	lastMatch := s.lastMatchUnix.Load()
	msgAge := int64(-1)
	if lastMsg > 0 {
		msgAge = now - lastMsg
		if msgAge < 0 {
			msgAge = 0
		}
	}
	matchAge := int64(-1)
	if lastMatch > 0 {
		matchAge = now - lastMatch
		if matchAge < 0 {
			matchAge = 0
		}
	}
	connected := s.connected.Load()
	if s.client != nil && s.client.IsConnected() {
		connected = true
	}
	return Stats{
		Connected:       connected,
		MessagesTotal:   s.messagesTotal.Load(),
		LastMsgUnix:     lastMsg,
		LastMsgAgeSec:   msgAge,
		MatchesTotal:    s.matchesTotal.Load(),
		LastMatchUnix:   lastMatch,
		LastMatchAgeSec: matchAge,
	}
}
