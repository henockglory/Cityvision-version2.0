package camera

import "testing"

func TestNormalizeHost(t *testing.T) {
	tests := []struct {
		in, want string
	}{
		{"192.168.1.108/32", "192.168.1.108"},
		{"192.168.1.108", "192.168.1.108"},
		{" 10.0.0.5/24 ", "10.0.0.5"},
		{"", ""},
	}
	for _, tc := range tests {
		if got := NormalizeHost(tc.in); got != tc.want {
			t.Errorf("NormalizeHost(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}
