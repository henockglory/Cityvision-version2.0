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

// ErrServiceNotRegistered is returned when a control action is attempted on a
// service that has not been registered yet (registration needs register-service.bat).
var ErrServiceNotRegistered = errors.New("service not registered — run register-service.bat (Windows)")

// ErrServiceNeedsRepair is returned when the Windows service runs under an account
// incompatible with WSL (e.g. LocalSystem).
var ErrServiceNeedsRepair = errors.New("service needs repair — run register-service.bat")

// StreamEvent is emitted over SSE during uninstall.
type StreamEvent struct {
	Event   string `json:"event"`
	Message string `json:"message"`
	OK      bool   `json:"ok,omitempty"`
}

func ProjectRoot() string {
	if v := os.Getenv("PROJECT_ROOT"); v != "" {
		return v
	}
	if v := os.Getenv("CITEVISION_ROOT"); v != "" {
		return v
	}
	cwd, err := os.Getwd()
	if err != nil {
		return "."
	}
	dir := cwd
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
	return cwd
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func readStartMode(root string) string {
	data, err := os.ReadFile(filepath.Join(root, "installer", ".service_start_mode"))
	if err != nil {
		return "auto"
	}
	mode := strings.TrimSpace(string(data))
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

func windowsEffectiveStartMode(registered bool) string {
	if !registered {
		return ""
	}
	out, err := exec.Command(scBinary(), "qc", windowsServiceName).CombinedOutput()
	if err != nil {
		return ""
	}
	text := strings.ToUpper(string(out))
	if strings.Contains(text, "AUTO_START") {
		return "auto"
	}
	if strings.Contains(text, "DEMAND_START") {
		return "manual"
	}
	return ""
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
		st.ServiceName = windowsServiceName
		reg, running, state, account := windowsServiceStateDetailed()
		st.ServiceRegistered = reg
		st.ServiceRunning = running
		st.ServiceState = state
		st.ServiceAccount = account
		st.ServiceNeedsRepair = reg && !windowsServiceAccountOK(account)
		st.StartModeEffective = windowsEffectiveStartMode(reg)
		if st.StartModeEffective == "" {
			st.StartModeEffective = configured
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
	st := GetStatus()
	if st.ServiceNeedsRepair {
		return ErrServiceNeedsRepair
	}
	scMode := "demand"
	if mode == "auto" {
		scMode = "auto"
	}
	// Preferred path: direct sc.exe config (works without UAC thanks to the
	// service control rights granted at registration via sc sdset).
	if ok, denied, out := scDirect("config", windowsServiceName, "start=", scMode); ok {
		return nil
	} else if !denied {
		// A non-permission failure (e.g. service missing) - report it directly.
		if out != "" {
			return fmt.Errorf("%s", out)
		}
	}
	// Fallback: self-elevating PS1 (UAC) for older installs without granted rights.
	return runElevatedServicePS1(root, "-StartMode", mode)
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

// applyWindowsServiceAction starts or stops the citevision service. Stop always
// shuts down the WSL application stack; start uses sc.exe with PAUSED recovery.
func applyWindowsServiceAction(root, action string) error {
	if action == "stop" {
		if err := stopAppStack(root); err != nil {
			return err
		}
		st := GetStatus()
		if !st.ServiceRegistered || st.ServiceState == "STOPPED" {
			return nil
		}
		if st.ServiceNeedsRepair {
			return nil
		}
		if ok, _, out := scDirect("stop", windowsServiceName); ok {
			return nil
		} else if out != "" {
			return fmt.Errorf("%s", out)
		}
		return nil
	}

	st := GetStatus()
	if st.ServiceNeedsRepair {
		return ErrServiceNeedsRepair
	}
	if st.ServiceState == "PAUSED" || st.ServiceState == "START_PENDING" || st.ServiceState == "STOP_PENDING" {
		scDirect("stop", windowsServiceName)
		time.Sleep(2 * time.Second)
	}
	ok, _, out := scDirect("start", windowsServiceName)
	if !ok && (strings.Contains(out, "1056") || strings.Contains(strings.ToLower(out), "already")) {
		scDirect("stop", windowsServiceName)
		time.Sleep(2 * time.Second)
		ok, _, out = scDirect("start", windowsServiceName)
	}
	if !ok {
		if out != "" {
			return fmt.Errorf("%s", out)
		}
		return fmt.Errorf("failed to start service %s", windowsServiceName)
	}
	return waitForAppHealth(120 * time.Second)
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
	// Persist the preference but don't try to drive a non-existent service
	// (that would attempt a UAC-elevated registration from WSL, which fails).
	if cur := GetStatus(); !cur.ServiceRegistered {
		return SetStartModeResult{
			OK:                false,
			StartMode:         mode,
			ServiceRegistered: false,
			Message:           ErrServiceNotRegistered.Error(),
		}, ErrServiceNotRegistered
	}
	if cur.ServiceNeedsRepair {
		return SetStartModeResult{
			OK:                false,
			StartMode:         mode,
			ServiceRegistered: true,
			Message:           ErrServiceNeedsRepair.Error(),
		}, ErrServiceNeedsRepair
	}
	var applyErr error
	if effectivePlatform() == "windows" {
		applyErr = applyWindowsStartMode(root, mode)
	} else {
		applyErr = applyLinuxStartMode(root, mode)
	}
	st := GetStatus()
	res := SetStartModeResult{
		OK:                 applyErr == nil,
		StartMode:          mode,
		StartModeEffective: st.StartModeEffective,
		ServiceRegistered:  st.ServiceRegistered,
	}
	if applyErr != nil {
		res.Message = applyErr.Error()
		return res, applyErr
	}
	modeLbl := "automatic"
	if mode == "manual" {
		modeLbl = "manual"
	}
	res.Message = fmt.Sprintf("Start mode set to %s", modeLbl)
	return res, nil
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
		if !cur.ServiceRegistered {
			return SetStartModeResult{
				OK:                false,
				ServiceRegistered: false,
				Message:           ErrServiceNotRegistered.Error(),
			}, ErrServiceNotRegistered
		}
		if cur.ServiceNeedsRepair {
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
