package demo

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const targetFPS = 25
const minOutputBytes = 4096
const transcodeTimeout = 15 * time.Minute

func TranscodeForStream(ctx context.Context, inputPath, outputPath string) error {
	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil {
		return err
	}
	// Apply a per-transcode timeout so a hung ffmpeg cannot block indefinitely.
	tctx, cancel := context.WithTimeout(ctx, transcodeTimeout)
	defer cancel()

	enc := pickEncoder()
	slog.Info("demo: starting transcode", "encoder", enc, "input", inputPath, "output", outputPath)
	start := time.Now()

	if err := runTranscode(tctx, inputPath, outputPath, enc); err == nil {
		if err := validateOutput(outputPath); err == nil {
			slog.Info("demo: transcode done", "encoder", enc, "duration_ms", time.Since(start).Milliseconds())
			return nil
		}
		_ = os.Remove(outputPath)
	} else {
		slog.Warn("demo: transcode attempt failed", "encoder", enc, "error", err)
	}
	if enc != "x264" {
		slog.Info("demo: retrying transcode with x264 fallback")
		if err := runTranscode(tctx, inputPath, outputPath, "x264"); err != nil {
			slog.Error("demo: x264 fallback failed", "error", err)
			return err
		}
		if err := validateOutput(outputPath); err != nil {
			return err
		}
		slog.Info("demo: transcode done (x264 fallback)", "duration_ms", time.Since(start).Milliseconds())
		return nil
	}
	return fmt.Errorf("ffmpeg: transcode failed")
}

func runTranscode(ctx context.Context, inputPath, outputPath, enc string) error {
	var cmd *exec.Cmd
	if enc == "nvenc" {
		cmd = exec.CommandContext(ctx, "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
			"-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-i", inputPath,
			"-c:v", "h264_nvenc", "-preset", "p4", "-tune", "ll", "-rc", "cbr", "-b:v", "5M", "-maxrate", "5M", "-bufsize", "10M",
			"-bf", "0", "-g", strconv.Itoa(targetFPS), "-keyint_min", strconv.Itoa(targetFPS), "-forced-idr", "1",
			"-r", strconv.Itoa(targetFPS), "-fps_mode", "cfr", "-pix_fmt", "yuv420p",
			"-movflags", "+faststart", "-an", outputPath)
	} else {
		cmd = exec.CommandContext(ctx, "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
			"-i", inputPath,
			"-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
			"-bf", "0", "-g", strconv.Itoa(targetFPS), "-keyint_min", strconv.Itoa(targetFPS), "-sc_threshold", "0",
			"-r", strconv.Itoa(targetFPS), "-fps_mode", "cfr", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
			"-an", outputPath)
	}
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("ffmpeg (%s): %w: %s", enc, err, strings.TrimSpace(string(out)))
	}
	return nil
}

func validateOutput(path string) error {
	st, err := os.Stat(path)
	if err != nil {
		return err
	}
	if st.Size() < minOutputBytes {
		return fmt.Errorf("ffmpeg output empty (%d bytes)", st.Size())
	}
	return nil
}

func pickEncoder() string {
	if strings.EqualFold(os.Getenv("DEMO_FORCE_X264"), "true") || strings.EqualFold(os.Getenv("DEMO_FORCE_X264"), "1") {
		return "x264"
	}
	cmd := exec.Command("ffmpeg", "-hide_banner", "-encoders")
	b, err := cmd.CombinedOutput()
	if err != nil {
		return "x264"
	}
	if strings.Contains(string(b), "h264_nvenc") {
		if exec.Command("nvidia-smi").Run() == nil {
			return "nvenc"
		}
	}
	return "x264"
}

func Go2rtcStreamSource(localRelPath string) string {
	return fmt.Sprintf("ffmpeg:/videos/%s#video=copy#loop", strings.TrimPrefix(localRelPath, "/"))
}

func LocalStreamRelPath(orgID, videoID string) string {
	return filepath.ToSlash(filepath.Join("demo", orgID, videoID+"_stream.mp4"))
}

func VideosBasePath() string {
	if p := os.Getenv("VIDEOS_PATH"); p != "" {
		return p
	}
	if root := os.Getenv("PROJECT_ROOT"); root != "" {
		return filepath.Join(root, "data", "videos")
	}
	return filepath.Join("data", "videos")
}

func TempDir() string {
	return filepath.Join(VideosBasePath(), "demo", "tmp")
}

// FastTempStreamPath uses ext4 /tmp for ffmpeg output when VIDEOS_PATH is on slow /mnt/c.
func FastTempStreamPath(videoID string) string {
	return filepath.Join(os.TempDir(), "citevision-demo-"+videoID+"_stream.mp4")
}
