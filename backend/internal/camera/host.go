package camera

import (
	"net"
	"strings"
)

// NormalizeHost strips PostgreSQL INET CIDR suffixes (e.g. 192.168.1.108/32) and whitespace.
func NormalizeHost(host string) string {
	host = strings.TrimSpace(host)
	if host == "" {
		return host
	}
	if h, _, err := net.SplitHostPort(host); err == nil {
		host = h
	}
	if i := strings.Index(host, "/"); i >= 0 {
		host = host[:i]
	}
	if ip := net.ParseIP(host); ip != nil {
		return ip.String()
	}
	return host
}
