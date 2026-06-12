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

	"github.com/citevision/citevision/backend/internal/alerts"
	"github.com/citevision/citevision/backend/internal/audit"
	"github.com/citevision/citevision/backend/internal/auth"
	"github.com/citevision/citevision/backend/internal/camera"
	"github.com/citevision/citevision/backend/internal/config"
	"github.com/citevision/citevision/backend/internal/correlation"
	"github.com/citevision/citevision/backend/internal/dashboard"
	"github.com/citevision/citevision/backend/internal/db"
	"github.com/citevision/citevision/backend/internal/events"
	"github.com/citevision/citevision/backend/internal/handler"
	"github.com/citevision/citevision/backend/internal/health"
	"github.com/citevision/citevision/backend/internal/middleware"
	"github.com/citevision/citevision/backend/internal/rules"
	"github.com/citevision/citevision/backend/internal/seed"
	"github.com/citevision/citevision/backend/internal/spatial"
	"github.com/citevision/citevision/backend/internal/state"
	"github.com/citevision/citevision/backend/internal/watchlist"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		slog.Error("config load failed", "error", err)
		os.Exit(1)
	}

	log := config.NewLogger(cfg.LogLevel)
	log.Info("starting citevision api", "env", cfg.AppEnv, "addr", cfg.Addr())

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

	if err := seed.Run(ctx, pool, seed.Config{
		AdminEmail:    cfg.SeedAdminEmail,
		AdminPassword: cfg.SeedAdminPassword,
		TenantName:    cfg.SeedTenantName,
		TenantSlug:    cfg.SeedTenantSlug,
	}, log); err != nil {
		log.Error("seed failed", "error", err)
		os.Exit(1)
	}

	authSvc := auth.NewService(pool, cfg.JWTSecret, cfg.JWTAccessTTL, cfg.JWTRefreshTTL)
	auditSvc := audit.NewService(pool, cfg.AuditSignKey)
	cipher, err := camera.NewCredentialCipher(cfg.CameraCredentialKey)
	if err != nil {
		log.Error("camera cipher init failed", "error", err)
		os.Exit(1)
	}

	api := &handler.API{
		Auth:        authSvc,
		Audit:       auditSvc,
		Cameras:     camera.NewService(pool, cipher),
		Spatial:     spatial.NewService(pool),
		Events:      events.NewService(pool),
		Rules:       rules.NewService(pool),
		State:       state.NewService(pool),
		Correlation: correlation.NewService(pool),
		Alerts:      alerts.NewService(pool, cfg.MinIOBucket),
		Dashboard:   dashboard.NewService(pool),
		Watchlist:   watchlist.NewService(pool),
	}

	checker := health.NewChecker(pool)
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
		r.Post("/auth/login", api.Login)
		r.Post("/auth/refresh", api.Refresh)
		r.Post("/auth/logout", api.Logout)

		r.Group(func(r chi.Router) {
			r.Use(middleware.Auth(authSvc))

			r.Get("/auth/me", api.Me)
			r.Post("/auth/totp/setup", api.SetupTOTP)
			r.Post("/auth/totp/confirm", api.ConfirmTOTP)

			r.Route("/orgs/{orgID}", func(r chi.Router) {
				r.Use(middleware.RequireOrgAccess(authSvc))

				r.Get("/dashboard/summary", api.DashboardSummary)
				r.Get("/audit", api.ListAuditLog)

				r.Route("/cameras", func(r chi.Router) {
					r.Get("/", api.ListCameras)
					r.Post("/", api.CreateCamera)
					r.Get("/discover", api.DiscoverCameras)
					r.Route("/{cameraID}", func(r chi.Router) {
						r.Get("/", api.GetCamera)
						r.Put("/", api.UpdateCamera)
						r.Delete("/", api.DeleteCamera)
						r.Get("/rtsp", api.BuildRTSP)
						r.Post("/stream/test", api.TestCameraStream)
					})
				})

				r.Route("/zones", func(r chi.Router) {
					r.Get("/", api.ListZones)
					r.Post("/", api.CreateZone)
				})

				r.Route("/lines", func(r chi.Router) {
					r.Get("/", api.ListLines)
					r.Post("/", api.CreateLine)
				})

				r.Post("/events/ingest", api.IngestEvent)
				r.Get("/events", api.ListEvents)

				r.Route("/rules", func(r chi.Router) {
					r.Get("/", api.ListRules)
					r.Post("/", api.CreateRule)
				})

				r.Route("/state", func(r chi.Router) {
					r.Put("/", api.UpsertState)
					r.Get("/{entityType}/{entityID}", api.GetState)
				})

				r.Get("/correlation/rules", api.ListCorrelationRules)

				r.Route("/alerts", func(r chi.Router) {
					r.Get("/", api.ListAlerts)
					r.Post("/", api.CreateAlert)
				})

				r.Route("/incidents", func(r chi.Router) {
					r.Get("/", api.ListIncidents)
					r.Post("/", api.CreateIncident)
					r.Post("/{incidentID}/evidence", api.AddIncidentEvidence)
				})

				r.Route("/watchlist", func(r chi.Router) {
					r.Get("/", api.ListWatchlist)
					r.Post("/", api.CreateWatchlistEntry)
					r.Get("/face/match", api.MatchFace)
					r.Get("/anpr/match", api.MatchANPR)
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
