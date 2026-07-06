package demo

import (
	"os"
	"path/filepath"
	"strings"
)

// streamFileCandidates returns paths to try for a ready demo video (canonical + DB + mirrors).
func streamFileCandidates(orgID, videoID, storedPath string) []string {
	seen := map[string]struct{}{}
	add := func(p string) {
		p = strings.TrimSpace(p)
		if p == "" {
			return
		}
		if _, ok := seen[p]; ok {
			return
		}
		seen[p] = struct{}{}
	}

	canonical := filepath.Join(VideosBasePath(), "demo", orgID, videoID+"_stream.mp4")
	add(canonical)
	add(storedPath)

	for _, alt := range remapVideoRoots(storedPath) {
		add(alt)
	}
	for _, alt := range remapVideoRoots(canonical) {
		add(alt)
	}

	out := make([]string, 0, len(seen))
	for p := range seen {
		out = append(out, p)
	}
	// Prefer canonical first when present in list.
	sortCanonicalFirst(out, canonical)
	return out
}

func sortCanonicalFirst(paths []string, canonical string) {
	for i, p := range paths {
		if p == canonical {
			paths[0], paths[i] = paths[i], paths[0]
			return
		}
	}
}

func remapVideoRoots(p string) []string {
	if p == "" {
		return nil
	}
	targets := []string{
		os.Getenv("PROJECT_ROOT"),
		VideosBasePath(),
		filepath.Dir(VideosBasePath()),
	}
	var out []string
	for _, old := range []string{
		"/mnt/c/Users/gheno/citevision",
		"/mnt/c/Citevision",
		"/mnt/c/Users/gheno/citevision-v2",
	} {
		if !strings.HasPrefix(p, old) {
			continue
		}
		for _, t := range targets {
			if t == "" {
				continue
			}
			out = append(out, strings.Replace(p, old, filepath.Clean(t), 1))
		}
	}
	return out
}

func validStreamFile(path string) bool {
	st, err := os.Stat(path)
	return err == nil && st.Size() >= minOutputBytes
}

// materializeStreamFile copies the first existing candidate into canonical VIDEOS_PATH.
func materializeStreamFile(orgID, videoID, storedPath string) (string, bool) {
	candidates := streamFileCandidates(orgID, videoID, storedPath)
	canonical := filepath.Join(VideosBasePath(), "demo", orgID, videoID+"_stream.mp4")

	if validStreamFile(canonical) {
		return canonical, false
	}

	var source string
	for _, c := range candidates {
		if c == canonical {
			continue
		}
		if validStreamFile(c) {
			source = c
			break
		}
	}
	if source == "" {
		return "", false
	}
	if err := os.MkdirAll(filepath.Dir(canonical), 0o755); err != nil {
		return "", false
	}
	if err := copyFile(source, canonical); err != nil {
		return "", false
	}
	return canonical, true
}
