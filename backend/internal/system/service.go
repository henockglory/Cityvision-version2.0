package system

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"os/user"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

const (
	// windowsServiceName is the ASCII-only service name used since the PS1 rewrite.
	windowsServiceName = "citevision"
	linuxServiceName   = "citevision.service"
)

var startModeApplyMu sync.Mutex

// Status describes the CitéVision system service registration and runtime state.
type Status struct {
	Platform           string `json:"platform"`
	ServiceRegistered  bool   `json:"service_registered"`
	ServiceRunning     bool   `json:"service_running"`
	AppRunning         bool   `json:"app_running"`
	ServiceState       string `json:"service_state,omitempty"`
	ServiceAccount     string `json:"service_account,omitempty"`
	ServiceNeedsRepair bool   `json:"service_needs_repair"`
	StartMode          string `json:"start_mode"`
	StartModeEffective string `json:"start_mode_effective"`
	ServiceName        string `json:"service_name"`
}

// SetStartModeResult is returned after changing the configured start mode.
type SetStartModeResult struct {
	OK                 bool   `json:"ok"`
	StartMode          string `json:"start_mode"`
	StartModeEffective string `json:"start_mode_effective"`
	ServiceRegistered  bool   `json:"service_registered"`
	Message            string `json:"message"`
}

var ErrInvalidStartMode = errors.New("invalid start mode: must be auto or manual")

// ErrServiceNotRegistered is returned when startup has not been configured yet.
var ErrServiceNotRegistered = errors.New("startup not configured — run installation or start-citevision.bat (Windows)")

// ErrServiceNeedsRepair is retained for Linux; unused on Windows Task Scheduler path.
var ErrServiceNeedsRepair = errors.New("service needs repair")

// StreamEvent is emitted over SSE during uninstall.
type StreamEvent struct {
	Event   string `json:"event"`
	Message string `json:"message"`
	OK      bool   `json:"ok,omitempty"`
}

func findProjectRootFromDir(start string) string {
	dir := start
	for i := 0; i < 8; i++ {
		if fileExists(filepath.Join(dir, "scripts", "uninstall-all.sh")) {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	return ""
}

func hasInstallerStartState(root string) bool {
	if root == "" {
		return false
	}
	return fileExists(filepath.Join(root, "installer", ".service_start_mode")) ||
		fileExists(filepath.Join(root, "installer", ".startup_configured"))
}

// ProjectRoot resolves the CitéVision install tree. The runtime cwd tree wins when it
// carries installer state so Paramètres stays aligned with the path used by start-linux.sh
// even if .env still points at an old clone (e.g. citevision vs Citevision).
func ProjectRoot() string {
	if cwd, err := os.Getwd(); err == nil {
		if root := findProjectRootFromDir(cwd); root != "" && hasInstallerStartState(root) {
			return root
		}
	}
	if v := os.Getenv("PROJECT_ROOT"); v != "" {
		return v
	}
	if v := os.Getenv("CITEVISION_ROOT"); v != "" {
		return v
	}
	if cwd, err := os.Getwd(); err == nil {
		if root := findProjectRootFromDir(cwd); root != "" {
			return root
		}
		return cwd
	}
	return "."
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func trimBOM(s string) string {
	return strings.TrimPrefix(strings.TrimSpace(s), "\ufeff")
}

func readStartMode(root string) string {
	data, err := os.ReadFile(filepath.Join(root, "installer", ".service_start_mode"))
	if err != nil {
		return "auto"
	}
	mode := strings.TrimSpace(string(data))
	mode = trimBOM(mode)
	if idx := strings.Index(mode, "|"); idx >= 0 {
		mode = strings.TrimSpace(mode[:idx])
	}
	if mode == "auto" || mode == "manual" {
		return mode
	}
	return "auto"
}

func writeStartMode(root, mode string) error {
	if mode != "auto" && mode != "manual" {
		return ErrInvalidStartMode
	}
	dir := filepath.Join(root, "installer")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(dir, ".service_start_mode"), []byte(mode), 0o644)
}

func ValidStartMode(mode string) bool {
	return mode == "auto" || mode == "manual"
}

// StartModeVerifyResult is returned by install-time verification (installer + internal API).
type StartModeVerifyResult struct {
	OK                 bool   `json:"ok"`
	Expected           string `json:"expected"`
	StartMode          string `json:"start_mode"`
	StartModeEffective string `json:"start_mode_effective"`
	ProjectRoot        string `json:"project_root"`
	FileOK             bool   `json:"file_ok"`
	MarkerOK           bool   `json:"marker_ok"`
	MarkerMode         string `json:"marker_mode,omitempty"`
	OSEffectiveOK      bool   `json:"os_effective_ok"`
	ServiceRegistered  bool   `json:"service_registered"`
	Message            string `json:"message,omitempty"`
}

// VerifyStartMode checks that the configured and effective modes match expected.
func VerifyStartMode(expected string) StartModeVerifyResult {
	if !ValidStartMode(expected) {
		return StartModeVerifyResult{
			OK:      false,
			Message: "invalid expected mode",
		}
	}
	root := ProjectRoot()
	configured := readStartMode(root)
	st := GetStatus()
	fileOK := configured == expected
	markerPath := filepath.Join(root, "installer", ".startup_configured")
	markerMode := ""
	markerOK := fileExists(markerPath)
	if markerOK {
		if data, err := os.ReadFile(markerPath); err == nil {
			parts := strings.SplitN(strings.TrimSpace(string(data)), "|", 2)
			markerMode = trimBOM(strings.TrimSpace(parts[0]))
		}
	}
	markerMatch := markerOK && markerMode == expected
	osOK := st.StartModeEffective == expected
	res := StartModeVerifyResult{
		Expected:           expected,
		StartMode:          configured,
		StartModeEffective: st.StartModeEffective,
		ProjectRoot:        root,
		FileOK:             fileOK,
		MarkerOK:           markerMatch,
		MarkerMode:         markerMode,
		OSEffectiveOK:      osOK,
		ServiceRegistered:  st.ServiceRegistered,
	}
	res.OK = fileOK && markerMatch && osOK
	if !res.OK {
		var parts []string
		if !fileOK {
			parts = append(parts, fmt.Sprintf("fichier=%q", configured))
		}
		if !markerMatch {
			parts = append(parts, fmt.Sprintf("marqueur=%q", markerMode))
		}
		if !osOK {
			parts = append(parts, fmt.Sprintf("effectif=%q", st.StartModeEffective))
		}
		res.Message = "désynchronisation: " + strings.Join(parts, ", ")
	}
	return res
}

// isWSL reports whether the backend runs inside WSL (a Linux process on a
// Windows host). In that case the OS service manager is the Windows SCM
// (NSSM service "citevision"), not systemd, and we drive it via interop.
func isWSL() bool {
	if runtime.GOOS != "linux" {
		return false
	}
	if os.Getenv("WSL_DISTRO_NAME") != "" || os.Getenv("WSL_INTEROP") != "" {
		return true
	}
	if data, err := os.ReadFile("/proc/sys/kernel/osrelease"); err == nil {
		s := strings.ToLower(string(data))
		if strings.Contains(s, "microsoft") || strings.Contains(s, "wsl") {
			return true
		}
	}
	return false
}

// effectivePlatform returns "windows" for native Windows or WSL-on-Windows
// (both controlled through the Windows SCM), otherwise the Go runtime OS.
func effectivePlatform() string {
	if runtime.GOOS == "windows" || isWSL() {
		return "windows"
	}
	return runtime.GOOS
}

// scBinary / powershellBinary return the right executable name depending on
// whether we call them natively (Windows) or via WSL interop.
func scBinary() string {
	if runtime.GOOS == "windows" {
		return "sc"
	}
	return "sc.exe"
}

func powershellBinary() string {
	if runtime.GOOS == "windows" {
		return "powershell"
	}
	return "powershell.exe"
}

// toWindowsPath converts a path to its Windows form (needed when passing a
// WSL path to powershell.exe via interop).
func toWindowsPath(p string) string {
	if runtime.GOOS == "windows" {
		return p
	}
	if out, err := exec.Command("wslpath", "-w", p).Output(); err == nil {
		if s := strings.TrimSpace(string(out)); s != "" {
			return s
		}
	}
	// Fallback: /mnt/c/foo/bar -> C:\foo\bar
	if strings.HasPrefix(p, "/mnt/") && len(p) > 6 {
		drive := strings.ToUpper(string(p[5]))
		rest := strings.ReplaceAll(p[6:], "/", "\\")
		return drive + ":" + rest
	}
	return p
}

const (
	windowsAutoStartTask = "CiteVision-AutoStart"
	windowsWatchdogTask  = "CiteVision-Watchdog"
)

func windowsStartupConfigured(root string) bool {
	marker := filepath.Join(root, "installer", ".startup_configured")
	if fileExists(marker) {
		return true
	}
	if scheduledTaskExists(windowsAutoStartTask) {
		return true
	}
	mode := readStartMode(root)
	return mode == "manual" && fileExists(filepath.Join(root, "installer", ".service_start_mode"))
}

func scheduledTaskExists(name string) bool {
	out, err := exec.Command("schtasks", "/Query", "/TN", name).CombinedOutput()
	if err != nil {
		return false
	}
	return strings.Contains(string(out), name)
}

func windowsEffectiveStartMode(root string, configured bool) string {
	if !configured {
		return ""
	}
	mode := readStartMode(root)
	if mode == "manual" {
		if scheduledTaskExists(windowsAutoStartTask) ||
			windowsRegistryAutostartEnabled(root) ||
			windowsStartupFolderAutostartEnabled() {
			return "auto"
		}
		return "manual"
	}
	if scheduledTaskExists(windowsAutoStartTask) {
		return "auto"
	}
	if windowsRegistryAutostartEnabled(root) || windowsStartupFolderAutostartEnabled() {
		return "auto"
	}
	return mode
}

func windowsRegistryAutostartEnabled(root string) bool {
	check := `(Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'CiteVision' -ErrorAction SilentlyContinue).CiteVision`
	var out []byte
	var err error
	if runtime.GOOS == "windows" {
		out, err = exec.Command("powershell", "-NoProfile", "-NonInteractive", "-Command", check).CombinedOutput()
	} else if isWSL() {
		out, err = exec.Command("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", check).CombinedOutput()
	} else {
		return false
	}
	text := strings.TrimSpace(string(out))
	return err == nil && text != "" && strings.Contains(strings.ToLower(text), "citevision-autostart")
}

func windowsStartupFolderAutostartEnabled() bool {
	var out []byte
	var err error
	if isWSL() || runtime.GOOS == "windows" {
		out, err = exec.Command(powershellBinary(), "-NoProfile", "-NonInteractive", "-Command",
			`Test-Path (Join-Path ([Environment]::GetFolderPath('Startup')) 'CiteVision-AutoStart.cmd')`,
		).CombinedOutput()
	} else {
		return false
	}
	return err == nil && strings.Contains(strings.ToLower(string(out)), "true")
}

func windowsAutoWatchActive(root string) bool {
	if readStartMode(root) != "auto" {
		return false
	}
	if scheduledTaskExists(windowsAutoStartTask) {
		return true
	}
	if windowsRegistryAutostartEnabled(root) {
		return true
	}
	if windowsStartupFolderAutostartEnabled() {
		return true
	}
	if scheduledTaskExists(windowsWatchdogTask) {
		return true
	}
	return false
}

func linuxEffectiveStartMode(registered bool) string {
	if !registered {
		return ""
	}
	if _, err := exec.LookPath("systemctl"); err != nil {
		return ""
	}
	out, err := exec.Command("systemctl", "is-enabled", linuxServiceName).CombinedOutput()
	text := strings.TrimSpace(string(out))
	if err == nil && text == "enabled" {
		return "auto"
	}
	if text == "disabled" || text == "masked" {
		return "manual"
	}
	return ""
}

// GetStatus returns current service registration and runtime information.
func GetStatus() Status {
	root := ProjectRoot()
	configured := readStartMode(root)
	platform := effectivePlatform()
	st := Status{
		Platform:    platform,
		StartMode:   configured,
		ServiceName: linuxServiceName,
		AppRunning:  appHealthOK(),
	}
	if platform == "windows" {
		st.ServiceName = "CiteVision-Startup"
		configured := windowsStartupConfigured(root)
		st.ServiceRegistered = configured
		st.AppRunning = appHealthOK()
		st.ServiceRunning = windowsAutoWatchActive(root)
		st.StartModeEffective = windowsEffectiveStartMode(root, configured)
		if st.StartModeEffective == "" {
			st.StartModeEffective = readStartMode(root)
		}
		return st
	}
	st.ServiceRegistered, st.ServiceRunning = linuxServiceState()
	st.StartModeEffective = linuxEffectiveStartMode(st.ServiceRegistered)
	if st.StartModeEffective == "" {
		st.StartModeEffective = configured
	}
	return st
}

func appHealthOK() bool {
	client := &http.Client{Timeout: 3 * time.Second}
	resp, err := client.Get("http://127.0.0.1:8081/health")
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode >= 200 && resp.StatusCode < 500
}

func parseServicePS1Output(out string) (bool, string) {
	lines := strings.Split(out, "\n")
	for i := len(lines) - 1; i >= 0; i-- {
		line := strings.TrimSpace(lines[i])
		if !strings.HasPrefix(line, "{") {
			continue
		}
		var data map[string]interface{}
		if err := json.Unmarshal([]byte(line), &data); err != nil {
			continue
		}
        if ok, exists := data["service_ok"].(bool); exists {
			if ok {
				return true, ""
			}
			if errMsg, ok := data["error"].(string); ok && errMsg != "" {
				return false, errMsg
			}
			return false, "service registration failed"
		}
		if ok, exists := data["startup_ok"].(bool); exists {
			if ok {
				return true, ""
			}
			if errMsg, ok := data["error"].(string); ok && errMsg != "" {
				return false, errMsg
			}
			return false, "startup configuration failed"
		}
	}
	if strings.TrimSpace(out) != "" {
		return false, strings.TrimSpace(out)
	}
	return false, "no response from install script"
}

// scDirect runs an sc.exe command and reports success plus whether the failure
// was an access-denied (so the caller can fall back to elevation).
func scDirect(args ...string) (ok bool, denied bool, out string) {
	raw, err := exec.Command(scBinary(), args...).CombinedOutput()
	out = strings.TrimSpace(string(raw))
	if err == nil {
		return true, false, out
	}
	low := strings.ToLower(out)
	// sc.exe access-denied: exit code 5 / "access is denied" / FR "acces refuse".
	if strings.Contains(low, "denied") || strings.Contains(low, "refus") ||
		strings.Contains(out, "OpenService FAILED 5") || strings.Contains(out, ":5") {
		denied = true
	}
	if ee, isExit := err.(*exec.ExitError); isExit && ee.ExitCode() == 5 {
		denied = true
	}
	return false, denied, out
}

func applyWindowsStartMode(root, mode string) error {
	return runInstallStartupPS1(root, mode)
}

func parseStartupResultFile(path string) (bool, string) {
	data, err := os.ReadFile(path)
	if err != nil {
		return false, ""
	}
	var payload map[string]interface{}
	if err := json.Unmarshal(data, &payload); err != nil {
		return false, ""
	}
	if ok, exists := payload["startup_ok"].(bool); exists {
		if ok {
			return true, ""
		}
		if errMsg, ok := payload["error"].(string); ok && errMsg != "" {
			return false, errMsg
		}
		return false, "startup configuration failed"
	}
	if ok, exists := payload["service_ok"].(bool); exists {
		if ok {
			return true, ""
		}
		if errMsg, ok := payload["error"].(string); ok && errMsg != "" {
			return false, errMsg
		}
		return false, "startup configuration failed"
	}
	return false, ""
}

func runInstallStartupPS1(root, mode string) error {
	ps1 := filepath.Join(root, "installer", "windows", "install-startup.ps1")
	if !fileExists(ps1) {
		// Preference already saved by SetStartMode; missing script is non-blocking.
		return nil
	}
	logsDir := filepath.Join(root, "logs")
	_ = os.MkdirAll(logsDir, 0o755)
	resultFile := filepath.Join(logsDir, "startup-result.json")
	_ = os.Remove(resultFile)

	args := []string{
		"-NoLogo", "-NonInteractive", "-NoProfile", "-ExecutionPolicy", "Bypass",
		"-File", toWindowsPath(ps1),
		"-StartMode", mode,
		"-Root", toWindowsPath(root),
		"-ResultFile", toWindowsPath(resultFile),
	}

	var out []byte
	if isWSL() {
		cmdArgs := append([]string{"/c", powershellBinary()}, args...)
		out, _ = exec.Command("cmd.exe", cmdArgs...).CombinedOutput()
	} else {
		out, _ = exec.Command(powershellBinary(), args...).CombinedOutput()
	}

	if ok, _ := parseStartupResultFile(resultFile); ok {
		return nil
	}
	if ok, _ := parseServicePS1Output(string(out)); ok {
		return nil
	}
	// Script is designed to always persist preference; never block the UI.
	return nil
}

func stopAppStack(root string) error {
	stopScript := filepath.Join(root, "scripts", "stop-linux.sh")
	if !fileExists(stopScript) {
		return fmt.Errorf("stop script not found: %s", stopScript)
	}
	if runtime.GOOS == "linux" {
		out, err := exec.Command("bash", stopScript).CombinedOutput()
		if err != nil {
			text := strings.TrimSpace(string(out))
			if text == "" {
				text = err.Error()
			}
			return fmt.Errorf("%s", text)
		}
		return nil
	}
	wslScript := toWslPathForExec(stopScript)
	out, err := exec.Command("wsl", "--", "bash", wslScript).CombinedOutput()
	if err != nil {
		text := strings.TrimSpace(string(out))
		if text == "" {
			text = err.Error()
		}
		return fmt.Errorf("%s", text)
	}
	return nil
}

func toWslPathForExec(p string) string {
	if runtime.GOOS == "linux" && isWSL() {
		return p
	}
	if out, err := exec.Command("wsl", "--", "wslpath", "-a", p).Output(); err == nil {
		if s := strings.TrimSpace(string(out)); s != "" {
			return s
		}
	}
	return toWindowsPath(p)
}

// applyWindowsServiceAction starts or stops the WSL application stack (no SCM service).
func applyWindowsServiceAction(root, action string) error {
	if action == "stop" {
		return stopAppStack(root)
	}
	if appHealthOK() {
		return nil
	}
	if err := startAppStack(root); err != nil {
		return err
	}
	return waitForAppHealth(120 * time.Second)
}

func startAppStack(root string) error {
	startScript := filepath.Join(root, "scripts", "start-linux.sh")
	if !fileExists(startScript) {
		return fmt.Errorf("start script not found: %s", startScript)
	}
	if runtime.GOOS == "linux" {
		out, err := exec.Command("bash", startScript).CombinedOutput()
		if err != nil {
			text := strings.TrimSpace(string(out))
			if text == "" {
				text = err.Error()
			}
			return fmt.Errorf("%s", text)
		}
		return nil
	}
	wslRoot := toWslPathForExec(root)
	cmd := fmt.Sprintf("cd '%s' && bash scripts/start-linux.sh", wslRoot)
	out, err := exec.Command("wsl", "--", "bash", "-lc", cmd).CombinedOutput()
	if err != nil {
		text := strings.TrimSpace(string(out))
		if text == "" {
			text = err.Error()
		}
		return fmt.Errorf("%s", text)
	}
	return nil
}

func waitForAppHealth(timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if appHealthOK() {
			return nil
		}
		time.Sleep(2 * time.Second)
	}
	return fmt.Errorf("application did not become healthy within %s", timeout)
}

// runElevatedServicePS1 invokes install-service.ps1 (which self-elevates via
// UAC) as a fallback when direct sc.exe control is denied.
func runElevatedServicePS1(root string, psArgs ...string) error {
	ps1 := filepath.Join(root, "installer", "windows", "install-service.ps1")
	if !fileExists(ps1) {
		return fmt.Errorf("install script not found: %s", ps1)
	}
	args := append([]string{
		"-NoLogo", "-NonInteractive", "-NoProfile", "-ExecutionPolicy", "Bypass",
		"-File", toWindowsPath(ps1),
	}, psArgs...)
	out, err := exec.Command(powershellBinary(), args...).CombinedOutput()
	if err == nil {
		return nil
	}
	ok, msg := parseServicePS1Output(string(out))
	if ok {
		return nil
	}
	if scOut, scErr := exec.Command(scBinary(), "query", windowsServiceName).CombinedOutput(); scErr == nil {
		if strings.Contains(string(scOut), "SERVICE_NAME") {
			return nil
		}
	}
	if msg != "" {
		return fmt.Errorf("%s", msg)
	}
	return fmt.Errorf("windows service operation failed: %v", err)
}

// applyLinuxServiceAction starts or stops citevision.service via systemd.
func applyLinuxServiceAction(root, action string) error {
	if action == "stop" {
		if err := stopAppStack(root); err != nil {
			return err
		}
	}
	if _, err := exec.LookPath("systemctl"); err != nil {
		if action == "stop" {
			return nil
		}
		return fmt.Errorf("systemd not available")
	}
	out, err := exec.Command("sudo", "systemctl", action, linuxServiceName).CombinedOutput()
	if err != nil {
		text := strings.TrimSpace(string(out))
		if text == "" {
			text = err.Error()
		}
		return fmt.Errorf("%s", text)
	}
	if action == "start" {
		return waitForAppHealth(120 * time.Second)
	}
	return nil
}

func applyLinuxStartMode(root, mode string) error {
	script := filepath.Join(root, "installer", "linux", "install-service.sh")
	if !fileExists(script) {
		return fmt.Errorf("install script not found: %s", script)
	}
	if _, err := exec.LookPath("systemctl"); err != nil {
		return fmt.Errorf("systemd not available")
	}
	username := os.Getenv("USER")
	if username == "" {
		if u, err := user.Current(); err == nil {
			username = u.Username
		}
	}
	out, err := exec.Command(
		"sudo", "bash", script,
		fmt.Sprintf("--root=%s", root),
		fmt.Sprintf("--user=%s", username),
		fmt.Sprintf("--start-mode=%s", mode),
	).CombinedOutput()
	if err != nil {
		text := strings.TrimSpace(string(out))
		if text == "" {
			text = err.Error()
		}
		return fmt.Errorf("%s", text)
	}
	return nil
}

// SetStartMode persists the mode and applies it to the OS service manager.
func SetStartMode(mode string) (SetStartModeResult, error) {
	if !ValidStartMode(mode) {
		return SetStartModeResult{}, ErrInvalidStartMode
	}
	root := ProjectRoot()
	if err := writeStartMode(root, mode); err != nil {
		return SetStartModeResult{}, err
	}

	go func(r, m string) {
		startModeApplyMu.Lock()
		defer startModeApplyMu.Unlock()
		if readStartMode(r) != m {
			return
		}
		if effectivePlatform() == "windows" {
			_ = applyWindowsStartMode(r, m)
			return
		}
		_ = applyLinuxStartMode(r, m)
	}(root, mode)

	modeLbl := "automatic"
	if mode == "manual" {
		modeLbl = "manual"
	}
	st := GetStatus()
	st.StartMode = mode
	st.StartModeEffective = mode
	if mode == "manual" {
		st.ServiceRunning = false
	}
	return SetStartModeResult{
		OK:                 true,
		StartMode:          mode,
		StartModeEffective: mode,
		ServiceRegistered:  st.ServiceRegistered,
		Message:            fmt.Sprintf("Start mode set to %s", modeLbl),
	}, nil
}

// ValidServiceAction reports whether action is a supported start/stop action.
func ValidServiceAction(action string) bool {
	return action == "start" || action == "stop"
}

// ServiceAction starts or stops the platform service (Windows SCM or systemd).
func ServiceAction(action string) (SetStartModeResult, error) {
	if !ValidServiceAction(action) {
		return SetStartModeResult{}, fmt.Errorf("invalid action: must be start or stop")
	}
	cur := GetStatus()
	if action == "start" {
		if effectivePlatform() != "windows" && !cur.ServiceRegistered {
			return SetStartModeResult{
				OK:                false,
				ServiceRegistered: false,
				Message:           ErrServiceNotRegistered.Error(),
			}, ErrServiceNotRegistered
		}
		if cur.ServiceNeedsRepair && effectivePlatform() != "windows" {
			return SetStartModeResult{
				OK:                false,
				ServiceRegistered: true,
				Message:           ErrServiceNeedsRepair.Error(),
			}, ErrServiceNeedsRepair
		}
	} else if !cur.ServiceRegistered && !cur.AppRunning {
		return SetStartModeResult{
			OK:                false,
			ServiceRegistered: false,
			Message:           "application is not running",
		}, fmt.Errorf("application is not running")
	}
	// Stop always allowed when service exists (including LocalSystem repair) or app is up.
	root := ProjectRoot()
	var applyErr error
	if effectivePlatform() == "windows" {
		applyErr = applyWindowsServiceAction(root, action)
	} else {
		applyErr = applyLinuxServiceAction(root, action)
	}
	st := GetStatus()
	res := SetStartModeResult{
		OK:                 applyErr == nil,
		StartMode:          st.StartMode,
		StartModeEffective: st.StartModeEffective,
		ServiceRegistered:  st.ServiceRegistered,
	}
	if applyErr != nil {
		res.Message = applyErr.Error()
		return res, applyErr
	}
	verb := "started"
	if action == "stop" {
		verb = "stopped"
	}
	res.Message = fmt.Sprintf("Application %s", verb)
	return res, nil
}

func windowsServiceAccountOK(account string) bool {
	account = strings.TrimSpace(account)
	if account == "" {
		return false
	}
	low := strings.ToLower(account)
	bad := []string{"localsystem", "local service", "networkservice", "nt authority\\localservice", "nt authority\\networkservice"}
	for _, b := range bad {
		if low == b {
			return false
		}
	}
	return true
}

func parseScState(text string) string {
	for _, line := range strings.Split(text, "\n") {
		upper := strings.ToUpper(line)
		if !strings.Contains(upper, "STATE") {
			continue
		}
		colon := strings.Index(line, ":")
		if colon < 0 {
			continue
		}
		fields := strings.Fields(strings.TrimSpace(line[colon+1:]))
		if len(fields) >= 2 {
			return strings.ToUpper(fields[1])
		}
		if len(fields) == 1 {
			return strings.ToUpper(fields[0])
		}
	}
	return ""
}

func parseScAccount(text string) string {
	for _, line := range strings.Split(text, "\n") {
		if strings.Contains(line, "SERVICE_START_NAME") {
			parts := strings.SplitN(line, ":", 2)
			if len(parts) == 2 {
				return strings.TrimSpace(parts[1])
			}
		}
	}
	return ""
}

func windowsServiceStateDetailed() (registered, running bool, state, account string) {
	qOut, qErr := exec.Command(scBinary(), "query", windowsServiceName).CombinedOutput()
	qText := string(qOut)
	if qErr != nil || !strings.Contains(qText, "SERVICE_NAME") {
		return false, false, "", ""
	}
	registered = true
	state = parseScState(qText)
	running = state == "RUNNING"

	cOut, _ := exec.Command(scBinary(), "qc", windowsServiceName).CombinedOutput()
	account = parseScAccount(string(cOut))
	return registered, running, state, account
}

func windowsServiceState() (registered, running bool) {
	reg, run, _, _ := windowsServiceStateDetailed()
	return reg, run
}

func linuxServiceState() (registered, running bool) {
	if _, err := exec.LookPath("systemctl"); err != nil {
		return false, false
	}
	out, err := exec.Command("systemctl", "status", linuxServiceName).CombinedOutput()
	text := string(out)
	if err != nil && !strings.Contains(text, "Loaded:") {
		return false, false
	}
	registered = strings.Contains(text, "Loaded: loaded") ||
		strings.Contains(text, "/etc/systemd/system/citevision.service")
	running = strings.Contains(text, "Active: active (running)")
	return registered, running
}

// ValidMode returns true if mode is a known uninstall mode.
func ValidMode(mode string) bool {
	switch mode {
	case "restart", "soft", "standard", "full", "nuclear":
		return true
	}
	return false
}

// modeToArgs maps an uninstall mode to script arguments.
// keepData legacy flag is used when mode is empty (backward compat).
func modeToArgs(mode string, keepData bool, isWindows bool) []string {
	if isWindows {
		switch mode {
		case "restart":
			return []string{"-Mode", "restart"}
		case "soft":
			return []string{"-Mode", "soft"}
		case "standard":
			return []string{"-Mode", "standard"}
		case "full":
			return []string{"-Mode", "full"}
		case "nuclear":
			return []string{"-Mode", "nuclear"}
		default:
			// legacy keep_data flag
			if keepData {
				return []string{"-KeepData"}
			}
			return nil
		}
	}
	// Linux / bash
	switch mode {
	case "restart":
		return []string{"--mode=restart"}
	case "soft":
		return []string{"--mode=soft"}
	case "standard":
		return []string{"--mode=standard"}
	case "full":
		return []string{"--mode=full"}
	case "nuclear":
		return []string{"--mode=nuclear"}
	default:
		if keepData {
			return []string{"--keep-data"}
		}
		return nil
	}
}

// UninstallStream runs the platform uninstall script and yields SSE events.
// mode is one of: restart, soft, standard, full, nuclear (empty = legacy keepData).
func UninstallStream(ctx context.Context, mode string, keepData bool) <-chan StreamEvent {
	ch := make(chan StreamEvent)
	go func() {
		defer close(ch)
		root := ProjectRoot()
		var cmd *exec.Cmd
		if runtime.GOOS == "windows" {
			extraArgs := modeToArgs(mode, keepData, true)
			args := []string{"-NoLogo", "-NonInteractive", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
				filepath.Join(root, "scripts", "uninstall-all.ps1"), "-Yes"}
			args = append(args, extraArgs...)
			cmd = exec.CommandContext(ctx, "powershell", args...)
		} else {
			extraArgs := modeToArgs(mode, keepData, false)
			args := []string{filepath.Join(root, "scripts", "uninstall-all.sh"), "--yes"}
			args = append(args, extraArgs...)
			cmd = exec.CommandContext(ctx, "bash", args...)
		}
		cmd.Dir = root
		// Merge stdout+stderr into a single pipe to avoid sequential read deadlock.
		cmd.Stderr = nil
		cmd.Stdout = nil
		pr, pw, err := os.Pipe()
		if err != nil {
			ch <- StreamEvent{Event: "error", Message: fmt.Sprintf("pipe failed: %v", err), OK: false}
			return
		}
		cmd.Stdout = pw
		cmd.Stderr = pw

		if err := cmd.Start(); err != nil {
			pw.Close()
			pr.Close()
			ch <- StreamEvent{Event: "error", Message: fmt.Sprintf("start failed: %v", err), OK: false}
			return
		}

		modeLabel := mode
		if modeLabel == "" {
			modeLabel = "standard"
		}
		ch <- StreamEvent{Event: "step", Message: fmt.Sprintf("Starting uninstall (mode: %s)...", modeLabel)}

		// Read merged output in a goroutine; close the write end once the process exits.
		var wg sync.WaitGroup
		wg.Add(1)
		go func() {
			defer wg.Done()
			streamLines(pr, ch)
		}()

		err = cmd.Wait()
		pw.Close() // signal EOF to the reader goroutine
		wg.Wait()
		pr.Close()

		if err != nil {
			ch <- StreamEvent{Event: "error", Message: fmt.Sprintf("Uninstall finished with errors: %v", err), OK: false}
			return
		}
		ch <- StreamEvent{
			Event:   "done",
			Message: "Uninstall complete - run setup.bat (Windows) or bash scripts/setup-wsl.sh (Linux) to reinstall.",
			OK:      true,
		}
	}()
	return ch
}

func streamLines(r io.Reader, ch chan<- StreamEvent) {
	sc := bufio.NewScanner(r)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		evt := "info"
		switch {
		case strings.Contains(line, "[ERR]"), strings.Contains(line, "ERROR"):
			evt = "error"
		case strings.Contains(line, "[WARN]"), strings.Contains(line, "WARN"):
			evt = "warn"
		case strings.Contains(line, "[OK]"):
			evt = "ok"
		case strings.Contains(line, "[INFO]"), strings.Contains(line, "==="):
			evt = "step"
		}
		ch <- StreamEvent{Event: evt, Message: line}
	}
}
