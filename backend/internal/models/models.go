package models

import (
	"encoding/json"
	"time"

	"github.com/google/uuid"
)

type Role string

const (
	RoleSuperAdmin Role = "super_admin"
	RoleOrgAdmin   Role = "org_admin"
	RoleOperator   Role = "operator"
	RoleAnalyst    Role = "analyst"
	RoleSupervisor Role = "supervisor"
	RoleViewer     Role = "viewer"
	RoleTechnician Role = "technician"
)

func (r Role) IsValid() bool {
	switch r {
	case RoleSuperAdmin, RoleOrgAdmin, RoleOperator, RoleAnalyst,
		RoleSupervisor, RoleViewer, RoleTechnician:
		return true
	default:
		return false
	}
}

type Organization struct {
	ID        uuid.UUID `json:"id"`
	Name      string    `json:"name"`
	Slug      string    `json:"slug"`
	IsActive  bool      `json:"is_active"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type User struct {
	ID           uuid.UUID `json:"id"`
	Email        string    `json:"email"`
	FullName     string    `json:"full_name"`
	IsActive     bool      `json:"is_active"`
	TOTPEnabled  bool      `json:"totp_enabled"`
	PasswordHash string    `json:"-"`
	TOTPSecret   *string   `json:"-"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
}

type Site struct {
	ID        uuid.UUID `json:"id"`
	OrgID     uuid.UUID `json:"org_id"`
	Name      string    `json:"name"`
	Slug      string    `json:"slug"`
	Timezone  string    `json:"timezone"`
	Address   *string   `json:"address,omitempty"`
	IsActive  bool      `json:"is_active"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type OrgMembership struct {
	ID        uuid.UUID `json:"id"`
	OrgID     uuid.UUID `json:"org_id"`
	UserID    uuid.UUID `json:"user_id"`
	RoleID    uuid.UUID `json:"role_id"`
	Role      Role      `json:"role"`
	CreatedAt time.Time `json:"created_at"`
}

type CameraVendor string

const (
	VendorDahua     CameraVendor = "dahua"
	VendorHikvision CameraVendor = "hikvision"
	VendorGeneric   CameraVendor = "generic"
)

type CameraStatus string

const (
	CameraOnline  CameraStatus = "online"
	CameraOffline CameraStatus = "offline"
	CameraUnknown CameraStatus = "unknown"
	CameraError   CameraStatus = "error"
)

type Camera struct {
	ID                uuid.UUID       `json:"id"`
	OrgID             uuid.UUID       `json:"org_id"`
	SiteID            uuid.UUID       `json:"site_id"`
	Name              string          `json:"name"`
	Vendor            CameraVendor    `json:"vendor"`
	Host              string          `json:"host"`
	Port              int             `json:"port"`
	Channel           int             `json:"channel"`
	Username          *string         `json:"username,omitempty"`
	PasswordEncrypted []byte          `json:"-"`
	RTSPPath          *string         `json:"rtsp_path,omitempty"`
	StreamProfile     string          `json:"stream_profile"`
	Status            CameraStatus    `json:"status"`
	Metadata          json.RawMessage `json:"metadata"`
	IsActive          bool            `json:"is_active"`
	CreatedAt         time.Time       `json:"created_at"`
	UpdatedAt         time.Time       `json:"updated_at"`
}

type Zone struct {
	ID        uuid.UUID       `json:"id"`
	OrgID     uuid.UUID       `json:"org_id"`
	SiteID    uuid.UUID       `json:"site_id"`
	CameraID  *uuid.UUID      `json:"camera_id,omitempty"`
	Name      string          `json:"name"`
	Polygon   json.RawMessage `json:"polygon"`
	Color     string          `json:"color"`
	ZoneKind  string          `json:"zone_kind,omitempty"`
	// BehaviorConfig holds the rich per-zone AI behavior: {"behavior":"<id>","config":{...}}.
	// Supersedes ZoneKind when a behavior is set. See shared/zone-behaviors.json.
	BehaviorConfig json.RawMessage `json:"behavior_config,omitempty"`
	IsActive       bool            `json:"is_active"`
	CreatedAt time.Time       `json:"created_at"`
	UpdatedAt time.Time       `json:"updated_at"`
}

type Line struct {
	ID         uuid.UUID       `json:"id"`
	OrgID      uuid.UUID       `json:"org_id"`
	SiteID     uuid.UUID       `json:"site_id"`
	CameraID   *uuid.UUID      `json:"camera_id,omitempty"`
	Name       string          `json:"name"`
	StartPoint json.RawMessage `json:"start_point"`
	EndPoint   json.RawMessage `json:"end_point"`
	Direction  *string         `json:"direction,omitempty"`
	// BehaviorConfig mirrors zones: {"behavior":"line_cross","config":{"class_filter":"...","direction":"..."}}.
	BehaviorConfig json.RawMessage `json:"behavior_config,omitempty"`
	IsActive       bool            `json:"is_active"`
	CreatedAt      time.Time       `json:"created_at"`
	UpdatedAt      time.Time       `json:"updated_at"`
}

type Event struct {
	ID               uuid.UUID       `json:"id"`
	OrgID            uuid.UUID       `json:"org_id"`
	SiteID           *uuid.UUID      `json:"site_id,omitempty"`
	CameraID         *uuid.UUID      `json:"camera_id,omitempty"`
	EventType        string          `json:"event_type"`
	Severity         string          `json:"severity"`
	Payload          json.RawMessage `json:"payload"`
	EvidenceSnapshot json.RawMessage `json:"evidence_snapshot,omitempty"`
	OccurredAt       time.Time       `json:"occurred_at"`
	IngestedAt       time.Time       `json:"ingested_at"`
}

type Rule struct {
	ID          uuid.UUID       `json:"id"`
	OrgID       uuid.UUID       `json:"org_id"`
	SiteID      *uuid.UUID      `json:"site_id,omitempty"`
	Name        string          `json:"name"`
	Description *string         `json:"description,omitempty"`
	Definition  json.RawMessage `json:"definition"`
	IsEnabled   bool            `json:"is_enabled"`
	Priority    int             `json:"priority"`
	CreatedAt   time.Time       `json:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at"`
}

type Alert struct {
	ID        uuid.UUID       `json:"id"`
	OrgID     uuid.UUID       `json:"org_id"`
	SiteID    *uuid.UUID      `json:"site_id,omitempty"`
	RuleID    *uuid.UUID      `json:"rule_id,omitempty"`
	EventID   *uuid.UUID      `json:"event_id,omitempty"`
	Title     string          `json:"title"`
	Message   *string         `json:"message,omitempty"`
	Severity  string          `json:"severity"`
	Status    string          `json:"status"`
	Metadata  json.RawMessage `json:"metadata"`
	CreatedAt time.Time       `json:"created_at"`
	UpdatedAt time.Time       `json:"updated_at"`
}

type Incident struct {
	ID          uuid.UUID       `json:"id"`
	OrgID       uuid.UUID       `json:"org_id"`
	SiteID      *uuid.UUID      `json:"site_id,omitempty"`
	Title       string          `json:"title"`
	Description *string         `json:"description,omitempty"`
	Status      string          `json:"status"`
	Severity    string          `json:"severity"`
	AssignedTo  *uuid.UUID      `json:"assigned_to,omitempty"`
	Metadata    json.RawMessage `json:"metadata"`
	CreatedAt   time.Time       `json:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at"`
	ResolvedAt  *time.Time      `json:"resolved_at,omitempty"`
}

type AuditEntry struct {
	ID           int64           `json:"id"`
	OrgID        *uuid.UUID      `json:"org_id,omitempty"`
	UserID       *uuid.UUID      `json:"user_id,omitempty"`
	Action       string          `json:"action"`
	ResourceType string          `json:"resource_type"`
	ResourceID   *string         `json:"resource_id,omitempty"`
	IPAddress    *string         `json:"ip_address,omitempty"`
	UserAgent    *string         `json:"user_agent,omitempty"`
	Payload      json.RawMessage `json:"payload"`
	PrevHash     string          `json:"prev_hash"`
	EntryHash    string          `json:"entry_hash"`
	CreatedAt    time.Time       `json:"created_at"`
}

type SetupStatus struct {
	Initialized bool `json:"initialized"`
}

type SetupCompleteRequest struct {
	OrgName       string `json:"org_name"`
	OrgSlug       string `json:"org_slug"`
	AdminEmail    string `json:"admin_email"`
	AdminPassword string `json:"admin_password"`
	AdminFullName string `json:"admin_full_name"`
}

type SetupCompleteResponse struct {
	OrgID  uuid.UUID `json:"org_id"`
	UserID uuid.UUID `json:"user_id"`
	SiteID uuid.UUID `json:"site_id"`
}
