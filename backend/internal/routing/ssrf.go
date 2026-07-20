package routing

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net"
	"net/url"
	"os"
	"strings"
)

// ValidateWebhookURL guards against SSRF: only http/https, and (by default)
// blocks loopback/private/link-local targets and the cloud metadata endpoint.
//
// Self-hosted automation (n8n/Make agents on the LAN) is supported via:
//   - WEBHOOK_ALLOW_PRIVATE=1            -> allow any private/loopback target
//   - WEBHOOK_ALLOWED_HOSTS=host1,host2  -> allowlist specific hosts (bypasses
//     the private-range check for those hosts only)
func ValidateWebhookURL(raw string) error {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil {
		return fmt.Errorf("invalid webhook URL: %w", err)
	}
	if u.Scheme != "http" && u.Scheme != "https" {
		return fmt.Errorf("webhook URL must be http or https")
	}
	host := u.Hostname()
	if host == "" {
		return fmt.Errorf("webhook URL has no host")
	}

	if os.Getenv("WEBHOOK_ALLOW_PRIVATE") == "1" {
		return nil
	}
	if hostInAllowlist(host) {
		return nil
	}

	ips, err := net.LookupIP(host)
	if err != nil {
		return fmt.Errorf("cannot resolve webhook host %q: %w", host, err)
	}
	for _, ip := range ips {
		if isBlockedIP(ip) {
			return fmt.Errorf("webhook host %q resolves to a blocked address (%s); "+
				"set WEBHOOK_ALLOW_PRIVATE=1 or WEBHOOK_ALLOWED_HOSTS to allow", host, ip)
		}
	}
	return nil
}

func hostInAllowlist(host string) bool {
	list := os.Getenv("WEBHOOK_ALLOWED_HOSTS")
	if strings.TrimSpace(list) == "" {
		return false
	}
	host = strings.ToLower(host)
	for _, h := range strings.Split(list, ",") {
		if strings.ToLower(strings.TrimSpace(h)) == host {
			return true
		}
	}
	return false
}

func isBlockedIP(ip net.IP) bool {
	if ip.IsLoopback() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() ||
		ip.IsMulticast() || ip.IsUnspecified() || ip.IsPrivate() {
		return true
	}
	// Cloud metadata endpoints (AWS/GCP/Azure IMDS).
	if ip.Equal(net.ParseIP("169.254.169.254")) || ip.Equal(net.ParseIP("fd00:ec2::254")) {
		return true
	}
	return false
}

// SigningEnabled reports whether outbound webhook signing is configured.
func SigningEnabled() bool {
	return os.Getenv("WEBHOOK_SIGNING_SECRET") != ""
}

// signBody returns the hex HMAC-SHA256 of body using WEBHOOK_SIGNING_SECRET,
// or "" when no secret is configured.
func signBody(body []byte) string {
	secret := os.Getenv("WEBHOOK_SIGNING_SECRET")
	if secret == "" {
		return ""
	}
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(body)
	return "sha256=" + hex.EncodeToString(mac.Sum(nil))
}
