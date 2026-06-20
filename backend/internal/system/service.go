package system

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
)

const (
	// windowsServiceName is the ASCII-only service name used since the PS1 rewrite.
	windowsServiceName = "CitevisionV2"
	linuxServiceName   = "citevision.service"
)

// Status describes the CitéVision system service registration and runtime state.
type Status struct {
	Platform          string `json:"platform"`
	ServiceRegistered bool   `json:"service_registered"`
	ServiceRunning    bool   `json:"service_running"`
	StartMode         string `json:"start_mode"`
	ServiceName       string `json:"service_name"`
}

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

// GetStatus returns current service registration and runtime information.
func GetStatus() Status {
	root := ProjectRoot()
	st := Status{
		Platform:    runtime.GOOS,
		StartMode:   readStartMode(root),
		ServiceName: linuxServiceName,
	}
	if runtime.GOOS == "windows" {
		st.ServiceName = windowsServiceName
		st.ServiceRegistered, st.ServiceRunning = windowsServiceState()
		return st
	}
	st.ServiceRegistered, st.ServiceRunning = linuxServiceState()
	return st
}

func windowsServiceState() (registered, running bool) {
	out, err := exec.Command("sc", "query", windowsServiceName).CombinedOutput()
	if err != nil {
		return false, false
	}
	text := string(out)
	if !strings.Contains(text, "SERVICE_NAME") {
		return false, false
	}
	registered = true
	running = strings.Contains(text, "RUNNING")
	return registered, running
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
			args := []string{"-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
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
