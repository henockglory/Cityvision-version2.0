package evaluator

import (
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"time"
)

// RuleSetState tracks distinct member event types matched within a window.
type RuleSetState struct {
	Matched   map[string]bool `json:"matched"`
	StartedAt time.Time       `json:"started_at"`
	FiredAt   time.Time       `json:"fired_at,omitempty"`
}

// RuleSetStore persists in-progress rule-set matches.
type RuleSetStore interface {
	Get(key string) (*RuleSetState, error)
	Set(key string, state RuleSetState, ttl time.Duration) error
	Delete(key string) error
}

type ruleSetMemEntry struct {
	state   RuleSetState
	expires time.Time
}

type MemoryRuleSetStore struct {
	mu   sync.Mutex
	data map[string]ruleSetMemEntry
}

func NewMemoryRuleSetStore() *MemoryRuleSetStore {
	return &MemoryRuleSetStore{data: make(map[string]ruleSetMemEntry)}
}

func (s *MemoryRuleSetStore) Get(key string) (*RuleSetState, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	entry, ok := s.data[key]
	if !ok || time.Now().After(entry.expires) {
		delete(s.data, key)
		return nil, nil
	}
	st := entry.state
	return &st, nil
}

func (s *MemoryRuleSetStore) Set(key string, state RuleSetState, ttl time.Duration) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.data[key] = ruleSetMemEntry{state: state, expires: time.Now().Add(ttl)}
	return nil
}

func (s *MemoryRuleSetStore) Delete(key string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.data, key)
	return nil
}

func evalRuleSet(node ConditionNode, def RuleDefinition, payload map[string]interface{}, now time.Time, store RuleSetStore) bool {
	if store == nil {
		store = NewMemoryRuleSetStore()
	}
	members := node.MemberEventTypes
	if len(members) == 0 {
		members = collectEventTypesFromNode(node)
	}
	if len(members) == 0 {
		if b := def.Bindings; b != nil {
			if raw, ok := b["member_event_types"].([]interface{}); ok {
				for _, v := range raw {
					members = append(members, fmt.Sprint(v))
				}
			}
		}
	}
	if len(members) == 0 {
		return false
	}
	et, _ := payload["event_type"].(string)
	if et == "" {
		if ev, ok := payload["event"].(string); ok {
			et = ev
		}
	}
	found := false
	for _, m := range members {
		if strings.EqualFold(m, et) {
			found = true
			break
		}
	}
	if !found {
		return false
	}
	minMatches := node.MinMatches
	if minMatches <= 0 {
		minMatches = 2
	}
	window := time.Duration(node.WindowSeconds) * time.Second
	if window <= 0 {
		window = 5 * time.Minute
	}
	keyFields := node.KeyFields
	if len(keyFields) == 0 {
		keyFields = []string{"camera_id"}
	}
	parts := []string{"ruleset", def.RuleID}
	for _, f := range keyFields {
		if v, ok := fieldValue(payload, f); ok {
			parts = append(parts, fmt.Sprintf("%v", v))
		}
	}
	key := strings.Join(parts, "|")

	state, _ := store.Get(key)
	if state == nil {
		state = &RuleSetState{Matched: map[string]bool{}, StartedAt: now}
	}
	if now.Sub(state.StartedAt) > window {
		state = &RuleSetState{Matched: map[string]bool{}, StartedAt: now}
	}
	state.Matched[et] = true
	distinct := len(state.Matched)
	_ = store.Set(key, *state, window*2)

	if distinct >= minMatches {
		_ = store.Delete(key)
		return true
	}
	return false
}

func collectEventTypesFromNode(node ConditionNode) []string {
	var out []string
	var walk func(ConditionNode)
	walk = func(n ConditionNode) {
		op := strings.ToUpper(n.Op)
		if op == "EQ" && (n.Field == "event_type" || n.Field == "event") {
			var v string
			_ = json.Unmarshal(n.Value, &v)
			if v != "" {
				out = append(out, v)
			}
		}
		for _, c := range n.Children {
			walk(c)
		}
	}
	walk(node)
	return out
}

func ObservationMode(def RuleDefinition) bool {
	if def.Bindings == nil {
		return false
	}
	v, ok := def.Bindings["observation_mode"].(bool)
	return ok && v
}

func HasCounterAction(actions []Action) bool {
	for _, a := range actions {
		if a.Type == "counter" {
			return true
		}
	}
	return false
}
