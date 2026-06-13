package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"

	"github.com/citevision/citevision-v2/backend/internal/alerts"
	"github.com/citevision/citevision-v2/backend/internal/audit"
	"github.com/citevision/citevision-v2/backend/internal/auth"
	"github.com/citevision/citevision-v2/backend/internal/camera"
	"github.com/citevision/citevision-v2/backend/internal/config"
	"github.com/citevision/citevision-v2/backend/internal/db"
	"github.com/citevision/citevision-v2/backend/internal/events"
	"github.com/citevision/citevision-v2/backend/internal/handler"
	"github.com/citevision/citevision-v2/backend/internal/health"
	"github.com/citevision/citevision-v2/backend/internal/middleware"
	"github.com/citevision/citevision-v2/backend/internal/rbac"
	redisstore "github.com/citevision/citevision-v2/backend/internal/redis"
	"github.com/citevision/citevision-v2/backend/internal/rules"
	"github.com/citevision/citevision-v2/backend/internal/setup"
	"github.com/citevision/citevision-v2/backend/internal/spatial"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		slog.Error("config load failed", "error", err)
		os.Exit(1)
	}

	log := config.NewLogger(cfg.LogLevel)
	log.Info("starting citevision v2 api", "env", cfg.AppEnv, "addr", cfg.Addr())

	ctx := context.Background()

	pool, err := db.Connect(ctx, cfg.PostgresURL)
	if err != nil {
		log.Error("database connect failed", "error", err)
		os.Exit(1)
	}
	defer pool.Close()

	migrationsPath := resolveMigrationsPath()
	if err := db.Migrate(cfg.PostgresURL, migrationsPath); err != nil {
		log.Error("migrations failed", "error", err, "path", migrationsPath)
		os.Exit(1)
	}
	log.Info("migrations applied", "path", migrationsPath)

	redisClient, err := redisstore.Connect(ctx, cfg.RedisURL, cfg.RedisPassword, cfg.JWTRefreshTTL)
	if err != nil {
		log.Error("redis connect failed", "error", err)
		os.Exit(1)
	}
	defer redisClient.Close()

	setupSvc := setup.NewService(pool)
	authSvc := auth.NewService(pool, redisClient, cfg.JWTSecret, cfg.JWTAccessTTL, cfg.JWTRefreshTTL)
	auditSvc := audit.NewService(pool, cfg.AuditSignKey)
	rbacSvc := rbac.NewService(pool)

	cipher, err := camera.NewCredentialCipher(cfg.CameraCredentialKey)
	if err != nil {
		log.Error("camera cipher init failed", "error", err)
		os.Exit(1)
	}

	api := &handler.API{
		Setup:   setupSvc,
		Auth:    authSvc,
		Audit:   auditSvc,
		Cameras: camera.NewService(pool, cipher),
		Spatial: spatial.NewService(pool),
		Events:  events.NewService(pool),
		Rules:   rules.NewService(pool),
		Alerts:  alerts.NewService(pool),
	}

	checker := health.NewChecker(pool, redisClient)
	r := chi.NewRouter()
	r.Use(chimw.RealIP)
	r.Use(chimw.RequestID)
	r.Use(middleware.CORS)
	r.Use(middleware.Logger(log))
	r.Use(middleware.Recoverer(log))

	r.Get("/health", checker.Live)
	r.Get("/health/ready", checker.Ready)
	r.Get("/metrics", health.MetricsHandler().ServeHTTP)

	r.Route("/api/v1", func(r chi.Router) {
		r.Get("/setup/status", api.SetupStatus)
		r.Post("/setup/complete", api.SetupComplete)

		r.Group(func(r chi.Router) {
			r.Use(middleware.RequireInitialized(setupSvc))

			r.Post("/auth/login", api.Login)
			r.Post("/auth/refresh", api.Refresh)

			r.Group(func(r chi.Router) {
				r.Use(middleware.Auth(authSvc))

				r.Get("/auth/me", api.Me)
				r.Post("/auth/logout", api.Logout)

				r.Route("/orgs/{orgID}", func(r chi.Router) {
					r.Use(middleware.RequireOrgAccess(authSvc))

					r.With(middleware.RequirePermission(rbacSvc, "audit:read")).Get("/audit", api.ListAuditLog)

					r.Route("/cameras", func(r chi.Router) {
						r.With(middleware.RequirePermission(rbacSvc, "cameras:read")).Get("/", api.ListCameras)
						r.With(middleware.RequirePermission(rbacSvc, "cameras:write")).Post("/", api.CreateCamera)
						r.With(middleware.RequirePermission(rbacSvc, "cameras:read")).Get("/discover", api.DiscoverCameras)
						r.Route("/{cameraID}", func(r chi.Router) {
							r.With(middleware.RequirePermission(rbacSvc, "cameras:read")).Get("/", api.GetCamera)
							r.With(middleware.RequirePermission(rbacSvc, "cameras:read")).Get("/rtsp", api.BuildRTSP)
							r.With(middleware.RequirePermission(rbacSvc, "cameras:read")).Post("/stream/test", api.TestCameraStream)
						})
					})

					r.Route("/zones", func(r chi.Router) {
						r.With(middleware.RequirePermission(rbacSvc, "zones:read")).Get("/", api.ListZones)
						r.With(middleware.RequirePermission(rbacSvc, "zones:write")).Post("/", api.CreateZone)
					})

					r.Route("/lines", func(r chi.Router) {
						r.With(middleware.RequirePermission(rbacSvc, "zones:read")).Get("/", api.ListLines)
						r.With(middleware.RequirePermission(rbacSvc, "zones:write")).Post("/", api.CreateLine)
					})

					r.With(middleware.RequirePermission(rbacSvc, "events:read")).Post("/events/ingest", api.IngestEvent)
					r.With(middleware.RequirePermission(rbacSvc, "events:read")).Get("/events", api.ListEvents)

					r.Route("/rules", func(r chi.Router) {
						r.With(middleware.RequirePermission(rbacSvc, "rules:read")).Get("/", api.ListRules)
						r.With(middleware.RequirePermission(rbacSvc, "rules:write")).Post("/", api.CreateRule)
						r.With(middleware.RequirePermission(rbacSvc, "rules:read")).Get("/active", api.ListActiveRules)
						r.With(middleware.RequirePermission(rbacSvc, "rules:simulate")).Post("/validate", api.ValidateRule)
						r.With(middleware.RequirePermission(rbacSvc, "rules:simulate")).Post("/evaluate", api.EvaluateRule)
						r.With(middleware.RequirePermission(rbacSvc, "rules:simulate")).Post("/{ruleID}/evaluate", api.EvaluateRule)
					})

					r.Route("/alerts", func(r chi.Router) {
						r.With(middleware.RequirePermission(rbacSvc, "alerts:read")).Get("/", api.ListAlerts)
						r.With(middleware.RequirePermission(rbacSvc, "alerts:ack")).Post("/", api.CreateAlert)
					})

					r.Route("/incidents", func(r chi.Router) {
						r.With(middleware.RequirePermission(rbacSvc, "alerts:read")).Get("/", api.ListIncidents)
						r.With(middleware.RequirePermission(rbacSvc, "alerts:ack")).Post("/", api.CreateIncident)
					})
				})
			})
		})
	})

	srv := &http.Server{
		Addr:         cfg.Addr(),
		Handler:      r,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		log.Info("listening", "addr", cfg.Addr())
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Error("server error", "error", err)
			os.Exit(1)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Info("shutting down")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Error("shutdown error", "error", err)
	}
}

func resolveMigrationsPath() string {
	candidates := []string{
		"migrations",
		filepath.Join("backend", "migrations"),
		filepath.Join("..", "migrations"),
	}
	for _, p := range candidates {
		if _, err := os.Stat(p); err == nil {
			abs, _ := filepath.Abs(p)
			return abs
		}
	}
	wd, _ := os.Getwd()
	return filepath.Join(wd, "migrations")
}
