package middleware

import (
	"context"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/auth"
	"github.com/citevision/citevision-v2/backend/internal/health"
	"github.com/citevision/citevision-v2/backend/internal/models"
	"github.com/citevision/citevision-v2/backend/internal/rbac"
	"github.com/citevision/citevision-v2/backend/internal/setup"
)

type contextKey string

const (
	ClaimsKey contextKey = "claims"
	OrgIDKey  contextKey = "org_id"
	RoleKey   contextKey = "org_role"
)

func Logger(log *slog.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			ww := chimw.NewWrapResponseWriter(w, r.ProtoMajor)
			next.ServeHTTP(ww, r)
			routePattern := chi.RouteContext(r.Context()).RoutePattern()
			if routePattern == "" {
				routePattern = r.URL.Path
			}
			log.Info("request",
				"method", r.Method,
				"path", r.URL.Path,
				"route", routePattern,
				"status", ww.Status(),
				"bytes", ww.BytesWritten(),
				"duration_ms", time.Since(start).Milliseconds(),
				"remote", r.RemoteAddr,
			)
			health.RecordRequest(r.Method, routePattern, ww.Status(), time.Since(start))
		})
	}
}

func Recoverer(log *slog.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			defer func() {
				if rec := recover(); rec != nil {
					log.Error("panic recovered", "error", rec)
					http.Error(w, `{"error":"internal server error"}`, http.StatusInternalServerError)
				}
			}()
			next.ServeHTTP(w, r)
		})
	}
}

func RequireInitialized(setupSvc *setup.Service) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			status, err := setupSvc.Status(r.Context())
			if err != nil || !status.Initialized {
				http.Error(w, `{"error":"setup required"}`, http.StatusServiceUnavailable)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

func Auth(authSvc *auth.Service) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			header := r.Header.Get("Authorization")
			if header == "" || !strings.HasPrefix(header, "Bearer ") {
				http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
				return
			}
			token := strings.TrimPrefix(header, "Bearer ")
			claims, err := authSvc.ParseAccessToken(token)
			if err != nil {
				http.Error(w, `{"error":"invalid token"}`, http.StatusUnauthorized)
				return
			}
			if err := authSvc.ValidateSession(r.Context(), claims); err != nil {
				http.Error(w, `{"error":"session expired"}`, http.StatusUnauthorized)
				return
			}
			ctx := context.WithValue(r.Context(), ClaimsKey, claims)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func RequireOrgAccess(authSvc *auth.Service) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			orgStr := chi.URLParam(r, "orgID")
			if orgStr == "" {
				orgStr = r.Header.Get("X-Org-ID")
			}
			if orgStr == "" {
				http.Error(w, `{"error":"org_id required"}`, http.StatusBadRequest)
				return
			}
			orgID, err := uuid.Parse(orgStr)
			if err != nil {
				http.Error(w, `{"error":"invalid org_id"}`, http.StatusBadRequest)
				return
			}
			claims := GetClaims(r.Context())
			if claims == nil {
				http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
				return
			}
			role, err := authSvc.HasOrgAccess(r.Context(), claims.UserID, orgID)
			if err != nil {
				http.Error(w, `{"error":"forbidden"}`, http.StatusForbidden)
				return
			}
			ctx := context.WithValue(r.Context(), OrgIDKey, orgID)
			ctx = context.WithValue(ctx, RoleKey, role)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func RequirePermission(rbacSvc *rbac.Service, permission string) func(http.Handler) http.Handler {
	return RequireAnyPermission(rbacSvc, permission)
}

func RequireOrgAdmin() func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			role := GetOrgRole(r.Context())
			if role == "" {
				claims := GetClaims(r.Context())
				if claims != nil {
					role = models.Role(claims.Role)
				}
			}
			if role != models.RoleOrgAdmin && role != models.RoleSuperAdmin {
				http.Error(w, `{"error":"forbidden"}`, http.StatusForbidden)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

func RequireAnyPermission(rbacSvc *rbac.Service, permissions ...string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			role := GetOrgRole(r.Context())
			if role == "" {
				claims := GetClaims(r.Context())
				if claims != nil {
					role = claims.Role
				}
			}
			for _, permission := range permissions {
				ok, err := rbacSvc.HasPermission(r.Context(), role, permission)
				if err == nil && ok {
					next.ServeHTTP(w, r)
					return
				}
			}
			http.Error(w, `{"error":"forbidden"}`, http.StatusForbidden)
		})
	}
}

func GetClaims(ctx context.Context) *auth.Claims {
	c, _ := ctx.Value(ClaimsKey).(*auth.Claims)
	return c
}

func GetOrgID(ctx context.Context) uuid.UUID {
	id, _ := ctx.Value(OrgIDKey).(uuid.UUID)
	return id
}

func GetOrgRole(ctx context.Context) models.Role {
	role, _ := ctx.Value(RoleKey).(models.Role)
	return role
}

func CORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Accept, Authorization, Content-Type, X-Org-ID")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}
