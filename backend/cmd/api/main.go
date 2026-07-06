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
	"github.com/citevision/citevision-v2/backend/internal/dashboard"
	"github.com/citevision/citevision-v2/backend/internal/db"
	"github.com/citevision/citevision-v2/backend/internal/demo"
	"github.com/citevision/citevision-v2/backend/internal/events"
	"github.com/citevision/citevision-v2/backend/internal/evidence"
	"github.com/citevision/citevision-v2/backend/internal/handler"
	"github.com/citevision/citevision-v2/backend/internal/health"
	"github.com/citevision/citevision-v2/backend/internal/identity"
	"github.com/citevision/citevision-v2/backend/internal/ingest"
	"github.com/citevision/citevision-v2/backend/internal/middleware"
	mqttsub "github.com/citevision/citevision-v2/backend/internal/mqtt"
	"github.com/citevision/citevision-v2/backend/internal/org"
	"github.com/citevision/citevision-v2/backend/internal/rbac"
	"github.com/citevision/citevision-v2/backend/internal/record"
	"github.com/citevision/citevision-v2/backend/internal/routing"
	redisstore "github.com/citevision/citevision-v2/backend/internal/redis"
	"github.com/citevision/citevision-v2/backend/internal/rules"
	"github.com/citevision/citevision-v2/backend/internal/setup"
	"github.com/citevision/citevision-v2/backend/internal/spatial"
	"github.com/citevision/citevision-v2/backend/internal/users"
	"github.com/citevision/citevision-v2/backend/internal/ws"
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

	alertsSvc := alerts.NewService(pool)
	orgSvc := org.NewService(pool)
	routingSvc := routing.NewService(pool)
	checker := health.NewChecker(pool, redisClient)
	alertHub := ws.NewHub(log)
	broadcaster := &mqttsub.Broadcaster{
		Hub:     alertHub,
		Alerts:  alertsSvc,
		Routing: routingSvc,
		Orgs:    orgSvc,
	}

	mqttBroker := os.Getenv("MQTT_BROKER")
	if mqttBroker == "" {
		host := os.Getenv("MQTT_HOST")
		if host == "" {
			host = "localhost"
		}
		port := os.Getenv("MQTT_PORT")
		if port == "" {
			port = "1884"
		}
		mqttBroker = "tcp://" + host + ":" + port
	}
	mqttSub := mqttsub.New(mqttBroker, broadcaster.HandleMQTTAlert, log)
	mqttCtx, mqttCancel := context.WithCancel(context.Background())
	defer mqttCancel()
	mqttSub.Start(mqttCtx)

	spatialSvc := spatial.NewService(pool)
	cameraSvc := camera.NewService(pool, cipher)
	evidenceSvc, err := evidence.NewService(evidence.ConfigFromEnv())
	if err != nil {
		log.Warn("evidence service init failed", "error", err)
	}
	if evidenceSvc != nil {
		routingSvc.SetAssetFetcher(evidenceSvc)
	}
	demoSvc := demo.NewServiceWithEvidence(pool, cameraSvc, evidenceSvc, log)
	if ms := demoSvc.MinioStore(); ms != nil && ms.Available() {
		if err := ms.EnsureBucket(ctx); err != nil {
			log.Warn("demo-videos bucket init failed", "error", err)
		}
	}
	go demoSvc.StartRetentionJanitor(mqttCtx)

	// Proactively repair demo video files + go2rtc streams (paths may differ across install roots).
	go func() {
		time.Sleep(5 * time.Second)
		tctx, tcancel := context.WithTimeout(context.Background(), 3*time.Minute)
		defer tcancel()
		demoSvc.RepairAllDemoStreams(tctx)
	}()

	eventsSvc := events.NewService(pool)
	eventIngestor := mqttsub.NewEventIngestor(pool, eventsSvc, demoSvc, mqttBroker, log)
	eventIngestor.Start(mqttCtx)

	go func() {
		time.Sleep(5 * time.Second)
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
		defer cancel()
		ok, failed := cameraSvc.ReOnboardAllRealCameras(ctx)
		if ok+failed > 0 {
			log.Info("camera streams re-onboarded on startup", "ok", ok, "failed", failed)
		}
	}()
	aiClient := ingest.NewAIClient(cfg)
	orch := ingest.NewOrchestrator(pool, aiClient, spatialSvc, cameraSvc, log)
	go orch.Run(mqttCtx)

	catalogPath := os.Getenv("RULE_CATALOG_PATH")
	if catalogPath == "" {
		catalogPath = "../shared/rule-catalog"
	}
	sharedPath := os.Getenv("SHARED_PATH")
	if sharedPath == "" {
		sharedPath = "../shared"
	}

	api := &handler.API{
		Setup:       setupSvc,
		Auth:        authSvc,
		Audit:       auditSvc,
		Cameras:     cameraSvc,
		Spatial:     spatialSvc,
		Events:      eventsSvc,
		Rules:       rules.NewService(pool),
		Identity:    identity.NewService(pool),
		Users:       users.NewService(pool),
		Alerts:      alertsSvc,
		Dashboard:   dashboard.NewService(pool),
		Orgs:        orgSvc,
		Routing:     routingSvc,
		Hub:         alertHub,
		CatalogPath: catalogPath,
		SharedPath:  sharedPath,
		Record:      record.NewService(pool, cameraSvc),
		Evidence:    evidenceSvc,
		AI:          aiClient,
		Orchestrator: orch,
		Demo:        demoSvc,
	}

	ws.ConfigureOrigins(cfg.WSAllowedOrigins)

	r := chi.NewRouter()
	r.Use(chimw.RealIP)
	r.Use(chimw.RequestID)
	r.Use(middleware.CORSWithConfig(cfg.CORSAllowedOrigins))
	r.Use(middleware.Logger(log))
	r.Use(middleware.Recoverer(log))

	// Rate limiters: strict on auth/setup (credential stuffing), moderate on
	// expensive discovery/forward endpoints.
	authLimiter := middleware.NewRateLimiter(30, 10)
	heavyLimiter := middleware.NewRateLimiter(60, 20)

	r.Get("/health", checker.Live)
	r.Get("/health/ready", checker.Ready)
	// /metrics is sensitive (info disclosure + DoS). Require the internal key
	// unless METRICS_PUBLIC=1 is explicitly set (e.g. behind a trusted proxy).
	if os.Getenv("METRICS_PUBLIC") == "1" {
		r.Get("/metrics", health.MetricsHandler().ServeHTTP)
	} else {
		r.With(middleware.RequireInternalKey).Get("/metrics", health.MetricsHandler().ServeHTTP)
	}

	r.Route("/api/v1", func(r chi.Router) {
		r.Get("/setup/status", api.SetupStatus)
		r.With(authLimiter.Middleware).Post("/setup/complete", api.SetupComplete)

		r.Route("/internal/orgs/{orgID}", func(r chi.Router) {
			r.Use(middleware.RequireInternalKey)
			r.Get("/rules/active", api.InternalListActiveRules)
			r.Post("/notify/email", api.InternalNotifyEmail)
			r.Post("/record/clip", api.InternalRecordClip)
			r.Post("/evidence/upload", api.InternalEvidenceUpload)
			r.Post("/evidence/request", api.InternalEvidenceRequest)
			r.Post("/incidents", api.InternalCreateIncident)
			r.Post("/alerts/archive", api.InternalArchiveAlert)
			r.Post("/alerts/archive-stale", api.InternalArchiveStaleAlerts)
			r.Post("/rules/counter", api.InternalIncrementRuleCounter)
			r.Post("/webhook", api.InternalWebhook)
			r.Get("/notification-defaults", api.InternalNotificationDefaults)
		})

		r.Route("/internal/ingest", func(r chi.Router) {
			r.Use(middleware.RequireInternalKey)
			r.Post("/resync-spatial", api.InternalResyncSpatial)
			r.Get("/orgs/{orgID}/cameras/{cameraID}/spatial-config", api.InternalDebugSpatialConfig)
		})

		r.Route("/internal/demo", func(r chi.Router) {
			r.Use(middleware.RequireInternalKey)
			r.Post("/repair-streams", api.InternalRepairDemoStreams)
		})

		r.Route("/internal/system", func(r chi.Router) {
			r.Use(middleware.RequireInternalKey)
			r.Get("/verify-start-mode", api.InternalVerifyStartMode)
			r.Post("/apply-start-mode", api.InternalApplyStartMode)
		})

		r.Group(func(r chi.Router) {
			r.Use(middleware.RequireInitialized(setupSvc))

			r.With(authLimiter.Middleware).Post("/auth/login", api.Login)
			r.With(authLimiter.Middleware).Post("/auth/refresh", api.Refresh)
			r.Get("/ws/alerts", api.WsAlerts)

			r.Group(func(r chi.Router) {
				r.Use(middleware.Auth(authSvc))

				r.Get("/auth/me", api.Me)
				r.Patch("/auth/me", api.UpdateMe)
				r.Post("/auth/logout", api.Logout)
				r.Post("/auth/totp/setup", api.StartTOTP)
				r.Post("/auth/totp/confirm", api.ConfirmTOTPSetup)

				r.Group(func(r chi.Router) {
					r.Use(middleware.RequireOrgAdmin())
					r.With(middleware.RequirePermission(rbacSvc, "system:health")).Get("/system/status", api.SystemStatus)
					r.With(middleware.RequirePermission(rbacSvc, "system:health")).Put("/system/start-mode", api.SystemSetStartMode)
					r.With(middleware.RequirePermission(rbacSvc, "system:health")).Post("/system/service-action", api.SystemServiceAction)
					r.With(middleware.RequirePermission(rbacSvc, "system:health")).Get("/system/uninstall/stream", api.SystemUninstallStream)
				})

				r.Route("/orgs/{orgID}", func(r chi.Router) {
					r.Use(middleware.RequireOrgAccess(authSvc))

					r.Get("/", api.GetOrganization)
					r.Patch("/", api.UpdateOrganization)
					r.Post("/integrations/smtp/test", api.TestSMTP)
					r.Get("/integrations/presets", api.ListIntegrationPresets)
					r.With(heavyLimiter.Middleware, middleware.RequirePermission(rbacSvc, "rules:write")).Post("/integrations/webhook/test", api.TestIntegrationWebhook)
					r.With(middleware.RequirePermission(rbacSvc, "alerts:read")).Get("/integrations/delivery-log", api.ListDeliveryLog)
					r.With(middleware.RequirePermission(rbacSvc, "system:health")).Post("/demo/reset", api.ResetDemoWorkspace)
					r.With(middleware.RequirePermission(rbacSvc, "system:health")).Post("/demo/purge-alerts", api.PurgeAlertsDemo)
					r.With(middleware.RequirePermission(rbacSvc, "cameras:read")).Get("/demo/settings", api.GetDemoSettings)
					r.With(middleware.RequirePermission(rbacSvc, "cameras:write")).Patch("/demo/settings", api.PatchDemoSettings)
					r.With(heavyLimiter.Middleware, middleware.RequirePermission(rbacSvc, "cameras:write")).Post("/demo/videos", api.UploadDemoVideo)
					r.With(middleware.RequirePermission(rbacSvc, "cameras:read")).Get("/demo/videos/{videoID}/status", api.GetDemoVideoStatus)
					r.With(middleware.RequirePermission(rbacSvc, "cameras:write")).Patch("/demo/videos/{videoID}", api.PatchDemoVideo)
					r.With(middleware.RequirePermission(rbacSvc, "cameras:write")).Post("/demo/videos/{videoID}/retry", api.RetryDemoVideo)
					r.With(middleware.RequirePermission(rbacSvc, "cameras:write")).Delete("/demo/videos/{videoID}", api.DeleteDemoVideo)
					r.With(middleware.RequirePermission(rbacSvc, "system:health")).Post("/maintenance/purge", api.PurgeOrgCommercial)

					r.With(middleware.RequirePermission(rbacSvc, "audit:read")).Get("/audit", api.ListAuditLog)
					r.With(middleware.RequirePermission(rbacSvc, "audit:read")).Get("/audit/verify", api.VerifyAuditChain)

					r.Route("/users", func(r chi.Router) {
						r.With(middleware.RequirePermission(rbacSvc, "users:read")).Get("/", api.ListUsers)
						r.With(middleware.RequirePermission(rbacSvc, "users:write")).Post("/", api.CreateUser)
						r.With(middleware.RequirePermission(rbacSvc, "users:write")).Patch("/{userID}", api.UpdateUser)
					})

					r.With(middleware.RequirePermission(rbacSvc, "system:health")).Get("/dashboard/summary", api.DashboardSummary)

					r.Route("/cameras", func(r chi.Router) {
						r.With(middleware.RequirePermission(rbacSvc, "cameras:read")).Get("/", api.ListCameras)
						r.With(middleware.RequirePermission(rbacSvc, "cameras:write")).Post("/", api.CreateCamera)
						r.With(heavyLimiter.Middleware, middleware.RequirePermission(rbacSvc, "cameras:read")).Get("/discover", api.DiscoverCameras)
						r.With(heavyLimiter.Middleware, middleware.RequirePermission(rbacSvc, "cameras:write")).Post("/probe", api.ProbeCamera)
						r.Route("/{cameraID}", func(r chi.Router) {
							r.With(middleware.RequirePermission(rbacSvc, "cameras:read")).Get("/", api.GetCamera)
							r.With(middleware.RequirePermission(rbacSvc, "cameras:write")).Patch("/", api.UpdateCamera)
							r.With(middleware.RequirePermission(rbacSvc, "cameras:write")).Delete("/", api.DeleteCamera)
							r.With(middleware.RequirePermission(rbacSvc, "cameras:read")).Get("/rtsp", api.BuildRTSP)
							r.With(middleware.RequirePermission(rbacSvc, "cameras:read")).Post("/stream/test", api.TestCameraStream)
							r.With(middleware.RequirePermission(rbacSvc, "cameras:read")).Get("/preview", api.CameraPreview)
						})
					})

					r.Route("/zones", func(r chi.Router) {
						r.With(middleware.RequirePermission(rbacSvc, "zones:read")).Get("/", api.ListZones)
						r.With(middleware.RequirePermission(rbacSvc, "zones:write")).Post("/", api.CreateZone)
						r.With(middleware.RequirePermission(rbacSvc, "zones:write")).Patch("/{zoneID}", api.UpdateZone)
						r.With(middleware.RequirePermission(rbacSvc, "zones:write")).Delete("/{zoneID}", api.DeleteZone)
					})

					r.Route("/lines", func(r chi.Router) {
						r.With(middleware.RequirePermission(rbacSvc, "zones:read")).Get("/", api.ListLines)
						r.With(middleware.RequirePermission(rbacSvc, "zones:read")).Get("/counters", api.ListLineCounters)
						r.With(middleware.RequirePermission(rbacSvc, "zones:write")).Delete("/counters", api.ResetLineCounters)
						r.With(middleware.RequirePermission(rbacSvc, "zones:write")).Post("/", api.CreateLine)
						r.With(middleware.RequirePermission(rbacSvc, "zones:write")).Patch("/{lineID}", api.UpdateLine)
						r.With(middleware.RequirePermission(rbacSvc, "zones:write")).Delete("/{lineID}", api.DeleteLine)
					})

					r.Route("/surveillance-lists", func(r chi.Router) {
						r.With(middleware.RequirePermission(rbacSvc, "rules:read")).Get("/", api.ListSurveillanceLists)
						r.With(middleware.RequirePermission(rbacSvc, "rules:write")).Post("/", api.CreateSurveillanceList)
						r.With(middleware.RequirePermission(rbacSvc, "rules:write")).Post("/{listID}/entries", api.AddSurveillanceListEntry)
						r.With(middleware.RequirePermission(rbacSvc, "rules:write")).Delete("/{listID}", api.DeleteSurveillanceList)
					})

					r.With(middleware.RequirePermission(rbacSvc, "events:read")).Post("/events/ingest", api.IngestEvent)
					r.With(middleware.RequirePermission(rbacSvc, "events:read")).Get("/events", api.ListEvents)
					r.With(middleware.RequireAnyPermission(rbacSvc, "events:read", "alerts:read")).Get("/evidence/asset", api.ServeEvidenceAsset)

					r.With(middleware.RequirePermission(rbacSvc, "system:health")).Get("/ai/model-pack", api.GetModelPack)
					r.With(middleware.RequirePermission(rbacSvc, "system:health")).Get("/ai/models", api.ListOrgAIModels)
					r.With(heavyLimiter.Middleware, middleware.RequirePermission(rbacSvc, "system:health")).Post("/ai/models", api.UploadOrgAIModel)

					r.Route("/capabilities", func(r chi.Router) {
						r.With(middleware.RequirePermission(rbacSvc, "rules:read")).Get("/menu", api.GetCapabilitiesMenu)
					})

					r.With(middleware.RequirePermission(rbacSvc, "rules:simulate")).Post("/scene-intent/validate", api.ValidateSceneIntent)

					r.Route("/rules", func(r chi.Router) {
						r.With(middleware.RequirePermission(rbacSvc, "rules:read")).Get("/", api.ListRules)
						r.With(middleware.RequirePermission(rbacSvc, "rules:read")).Get("/catalog", api.ListRuleCatalog)
						r.With(middleware.RequirePermission(rbacSvc, "rules:write")).Post("/", api.CreateRule)
						r.With(middleware.RequirePermission(rbacSvc, "rules:read")).Get("/active", api.ListActiveRules)
						r.With(middleware.RequirePermission(rbacSvc, "rules:write")).Patch("/{ruleID}", api.UpdateRule)
						r.With(middleware.RequirePermission(rbacSvc, "rules:write")).Delete("/{ruleID}", api.DeleteRule)
						r.With(middleware.RequirePermission(rbacSvc, "rules:simulate")).Post("/validate", api.ValidateRule)
						r.With(middleware.RequirePermission(rbacSvc, "rules:simulate")).Post("/evaluate", api.EvaluateRule)
						r.With(middleware.RequirePermission(rbacSvc, "rules:simulate")).Post("/{ruleID}/evaluate", api.EvaluateRule)
					})

					r.Route("/alerts", func(r chi.Router) {
						r.With(middleware.RequirePermission(rbacSvc, "alerts:read")).Get("/", api.ListAlerts)
						r.With(middleware.RequirePermission(rbacSvc, "alerts:ack")).Post("/", api.CreateAlert)
						r.With(heavyLimiter.Middleware, middleware.RequirePermission(rbacSvc, "alerts:ack")).Post("/{alertID}/forward", api.ForwardAlert)
						r.With(middleware.RequirePermission(rbacSvc, "alerts:ack")).Patch("/{alertID}/acknowledge", api.AcknowledgeAlert)
						r.With(middleware.RequirePermission(rbacSvc, "alerts:ack")).Patch("/{alertID}/archive", api.ArchiveAlert)
					})

					r.Route("/routing-rules", func(r chi.Router) {
						r.With(middleware.RequirePermission(rbacSvc, "rules:read")).Get("/", api.ListRoutingRules)
						r.With(middleware.RequirePermission(rbacSvc, "rules:write")).Post("/", api.CreateRoutingRule)
						r.With(middleware.RequirePermission(rbacSvc, "rules:write")).Patch("/{ruleID}", api.UpdateRoutingRule)
						r.With(middleware.RequirePermission(rbacSvc, "rules:write")).Delete("/{ruleID}", api.DeleteRoutingRule)
						r.With(middleware.RequirePermission(rbacSvc, "rules:simulate")).Post("/test", api.TestRoutingRules)
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
		Addr:              cfg.Addr(),
		Handler:           r,
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       0,
		WriteTimeout:      90 * time.Second,
		IdleTimeout:       60 * time.Second,
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

	// Stop background workers (MQTT subscribers, event ingestor, orchestrator)
	// first so they don't process while HTTP drains.
	mqttCancel()

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Error("shutdown error", "error", err)
	}
	// Give workers a brief moment to observe cancellation before exit.
	time.Sleep(200 * time.Millisecond)
	log.Info("shutdown complete")
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
