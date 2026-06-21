package ws

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"strings"
	"sync"

	"github.com/gorilla/websocket"
)

// allowedOrigins restricts WebSocket upgrades. Empty => same-origin/no-Origin
// and localhost dev origins only. A single "*" allows any origin.
var allowedOrigins []string

// ConfigureOrigins sets the WebSocket origin allowlist (call once at startup).
func ConfigureOrigins(origins []string) {
	allowedOrigins = origins
}

func originAllowed(r *http.Request) bool {
	origin := r.Header.Get("Origin")
	// Non-browser clients (no Origin header) are allowed; auth still applies.
	if origin == "" {
		return true
	}
	if len(allowedOrigins) == 1 && allowedOrigins[0] == "*" {
		return true
	}
	candidate := strings.ToLower(strings.TrimRight(origin, "/"))
	list := allowedOrigins
	if len(list) == 0 {
		list = []string{
			"http://localhost:5174", "http://127.0.0.1:5174",
			"http://localhost:5173", "http://127.0.0.1:5173",
		}
	}
	for _, o := range list {
		if strings.ToLower(strings.TrimRight(o, "/")) == candidate {
			return true
		}
	}
	return false
}

var upgrader = websocket.Upgrader{
	CheckOrigin: originAllowed,
}

type Hub struct {
	mu      sync.RWMutex
	clients map[*websocket.Conn]struct{}
	log     *slog.Logger
}

func NewHub(log *slog.Logger) *Hub {
	return &Hub{
		clients: make(map[*websocket.Conn]struct{}),
		log:     log,
	}
}

func (h *Hub) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		h.log.Error("websocket upgrade failed", "error", err)
		return
	}

	h.mu.Lock()
	h.clients[conn] = struct{}{}
	h.mu.Unlock()

	defer func() {
		h.mu.Lock()
		delete(h.clients, conn)
		h.mu.Unlock()
		_ = conn.Close()
	}()

	for {
		if _, _, err := conn.ReadMessage(); err != nil {
			break
		}
	}
}

func (h *Hub) Broadcast(v interface{}) {
	data, err := json.Marshal(v)
	if err != nil {
		return
	}
	h.mu.RLock()
	defer h.mu.RUnlock()
	for conn := range h.clients {
		if err := conn.WriteMessage(websocket.TextMessage, data); err != nil {
			_ = conn.Close()
			delete(h.clients, conn)
		}
	}
}

func (h *Hub) ClientCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.clients)
}
