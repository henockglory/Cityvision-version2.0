//go:build !linux && !darwin

package health

func diskUsage(path string) (map[string]interface{}, error) {
	return map[string]interface{}{"path": path, "used_percent": 0.0}, nil
}
