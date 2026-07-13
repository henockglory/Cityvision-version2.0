//go:build linux || darwin

package health

import "syscall"

// diskUsage returns used/total bytes and used_percent for a mount path (Linux/macOS).
func diskUsage(path string) (map[string]interface{}, error) {
	var st syscall.Statfs_t
	if err := syscall.Statfs(path, &st); err != nil {
		return nil, err
	}
	total := float64(st.Blocks) * float64(st.Bsize)
	free := float64(st.Bavail) * float64(st.Bsize)
	used := total - free
	pct := 0.0
	if total > 0 {
		pct = (used / total) * 100
	}
	return map[string]interface{}{
		"total_bytes":  total,
		"used_bytes":   used,
		"free_bytes":   free,
		"used_percent": pct,
	}, nil
}
