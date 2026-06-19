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
)

const (
	windowsServiceName = "CitéVision"
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

// UninstallStream runs the platform uninstall script and yields SSE events.
func UninstallStream(ctx context.Context, keepData bool) <-chan StreamEvent {
	ch := make(chan StreamEvent)
	go func() {
		defer close(ch)
		root := ProjectRoot()
		var cmd *exec.Cmd
		if runtime.GOOS == "windows" {
			args := []string{"-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
				filepath.Join(root, "scripts", "uninstall-all.ps1"), "-Yes"}
			if keepData {
				args = append(args, "-KeepData")
			}
			cmd = exec.CommandContext(ctx, "powershell", args...)
		} else {
			args := []string{filepath.Join(root, "scripts", "uninstall-all.sh"), "--yes"}
			if keepData {
				args = append(args, "--keep-data")
			}
			cmd = exec.CommandContext(ctx, "bash", args...)
		}
		cmd.Dir = root
		stdout, err := cmd.StdoutPipe()
		if err != nil {
			ch <- StreamEvent{Event: "error", Message: fmt.Sprintf("pipe failed: %v", err), OK: false}
			return
		}
		stderr, err := cmd.StderrPipe()
		if err != nil {
			ch <- StreamEvent{Event: "error", Message: fmt.Sprintf("pipe failed: %v", err), OK: false}
			return
		}
		if err := cmd.Start(); err != nil {
			ch <- StreamEvent{Event: "error", Message: fmt.Sprintf("start failed: %v", err), OK: false}
			return
		}

		ch <- StreamEvent{Event: "step", Message: "Démarrage de la désinstallation…"}
		streamLines(stdout, ch)
		streamLines(stderr, ch)

		err = cmd.Wait()
		if err != nil {
			ch <- StreamEvent{Event: "error", Message: fmt.Sprintf("Désinstallation terminée avec erreurs: %v", err), OK: false}
			return
		}
		ch <- StreamEvent{
			Event:   "done",
			Message: "Désinstallation terminée — relancez setup.bat pour réinstaller",
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
