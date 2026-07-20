package evidence

import "testing"

func TestNormalizeMinIOEndpoint(t *testing.T) {
	cases := map[string]string{
		"http://localhost:9003":  "localhost:9003",
		"https://minio:9000":     "minio:9000",
		"localhost:9003":         "localhost:9003",
		"  http://127.0.0.1:9003": "127.0.0.1:9003",
		"":                       "",
	}
	for in, want := range cases {
		if got := normalizeMinIOEndpoint(in); got != want {
			t.Fatalf("normalizeMinIOEndpoint(%q) = %q, want %q", in, got, want)
		}
	}
}
