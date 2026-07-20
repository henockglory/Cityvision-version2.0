package evaluator

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

// SequenceState tracks progress through a multi-step time-windowed rule.
type SequenceState struct {
	Step      int       `json:"step"`
	StartedAt time.Time `json:"started_at"`
}

// SequenceStore persists in-progress sequence matches across MQTT events.
type SequenceStore interface {
	Get(key string) (*SequenceState, error)
	Set(key string, state SequenceState, ttl time.Duration) error
	Delete(key string) error
}

type memoryEntry struct {
	state   SequenceState
	expires time.Time
}

// MemorySequenceStore is the default dev store (no Redis required).
type MemorySequenceStore struct {
	mu   sync.Mutex
	data map[string]memoryEntry
}

func NewMemorySequenceStore() *MemorySequenceStore {
	return &MemorySequenceStore{data: make(map[string]memoryEntry)}
}

func (s *MemorySequenceStore) Get(key string) (*SequenceState, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	entry, ok := s.data[key]
	if !ok || time.Now().After(entry.expires) {
		delete(s.data, key)
		return nil, nil
	}
	state := entry.state
	return &state, nil
}

func (s *MemorySequenceStore) Set(key string, state SequenceState, ttl time.Duration) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.data[key] = memoryEntry{state: state, expires: time.Now().Add(ttl)}
	return nil
}

func (s *MemorySequenceStore) Delete(key string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.data, key)
	return nil
}

// RedisSequenceStore shares sequence state across rules-engine replicas.
type RedisSequenceStore struct {
	client *redis.Client
	prefix string
}

func NewRedisSequenceStore(url string) (*RedisSequenceStore, error) {
	opts, err := redis.ParseURL(url)
	if err != nil {
		return nil, err
	}
	client := redis.NewClient(opts)
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if err := client.Ping(ctx).Err(); err != nil {
		return nil, err
	}
	prefix := os.Getenv("REDIS_SEQUENCE_PREFIX")
	if prefix == "" {
		prefix = "cv:rule-seq:"
	}
	return &RedisSequenceStore{client: client, prefix: prefix}, nil
}

func (s *RedisSequenceStore) redisKey(key string) string {
	return s.prefix + key
}

func (s *RedisSequenceStore) Get(key string) (*SequenceState, error) {
	ctx := context.Background()
	raw, err := s.client.Get(ctx, s.redisKey(key)).Bytes()
	if err == redis.Nil {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var state SequenceState
	if err := json.Unmarshal(raw, &state); err != nil {
		return nil, err
	}
	return &state, nil
}

func (s *RedisSequenceStore) Set(key string, state SequenceState, ttl time.Duration) error {
	raw, err := json.Marshal(state)
	if err != nil {
		return err
	}
	ctx := context.Background()
	return s.client.Set(ctx, s.redisKey(key), raw, ttl).Err()
}

func (s *RedisSequenceStore) Delete(key string) error {
	ctx := context.Background()
	return s.client.Del(ctx, s.redisKey(key)).Err()
}

// NewSequenceStoreFromEnv uses REDIS_URL when set, otherwise in-memory storage.
func NewSequenceStoreFromEnv() SequenceStore {
	if url := strings.TrimSpace(os.Getenv("REDIS_URL")); url != "" {
		if store, err := NewRedisSequenceStore(url); err == nil {
			return store
		}
	}
	return NewMemorySequenceStore()
}

func sequenceStateKey(ruleID string, keyFields []string, payload map[string]interface{}) string {
	parts := []string{ruleID}
	for _, f := range keyFields {
		if v, ok := fieldValue(payload, f); ok {
			parts = append(parts, fmt.Sprintf("%v", v))
		}
	}
	return strings.Join(parts, "|")
}

func evalSequence(node ConditionNode, def RuleDefinition, payload map[string]interface{}, now time.Time, store SequenceStore) bool {
	if store == nil {
		store = NewMemorySequenceStore()
	}
	steps := node.Children
	if len(steps) == 0 {
		return false
	}

	window := time.Duration(node.WindowSeconds) * time.Second
	if window <= 0 {
		window = 5 * time.Minute
	}
	keyFields := node.KeyFields
	if len(keyFields) == 0 {
		keyFields = []string{"camera_id", "track_id"}
	}

	stateKey := sequenceStateKey(def.RuleID, keyFields, payload)
	state, _ := store.Get(stateKey)

	stepIdx := 0
	startedAt := now
	if state != nil {
		if now.Sub(state.StartedAt) > window {
			_ = store.Delete(stateKey)
		} else {
			stepIdx = state.Step
			startedAt = state.StartedAt
		}
	}

	if stepIdx >= len(steps) {
		_ = store.Delete(stateKey)
		stepIdx = 0
		startedAt = now
	}

	if !evalCondition(steps[stepIdx], payload) {
		return false
	}

	nextStep := stepIdx + 1
	if nextStep >= len(steps) {
		_ = store.Delete(stateKey)
		return true
	}

	_ = store.Set(stateKey, SequenceState{Step: nextStep, StartedAt: startedAt}, window)
	return false
}
