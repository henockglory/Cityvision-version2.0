package routing

import "testing"

func TestValidateWebhookURL_Blocking(t *testing.T) {
	t.Setenv("WEBHOOK_ALLOW_PRIVATE", "")
	t.Setenv("WEBHOOK_ALLOWED_HOSTS", "")
	cases := []string{
		"http://127.0.0.1/hook",
		"http://localhost:8080/hook",
		"http://169.254.169.254/latest/meta-data/",
		"http://10.0.0.5/hook",
		"http://192.168.1.10/hook",
		"ftp://example.com/x",
		"file:///etc/passwd",
	}
	for _, c := range cases {
		if err := ValidateWebhookURL(c); err == nil {
			t.Errorf("expected %q to be blocked", c)
		}
	}
}

func TestValidateWebhookURL_AllowPrivateEnv(t *testing.T) {
	t.Setenv("WEBHOOK_ALLOW_PRIVATE", "1")
	if err := ValidateWebhookURL("http://127.0.0.1:5678/webhook/abc"); err != nil {
		t.Errorf("expected loopback allowed with WEBHOOK_ALLOW_PRIVATE=1, got %v", err)
	}
}

func TestValidateWebhookURL_Allowlist(t *testing.T) {
	t.Setenv("WEBHOOK_ALLOW_PRIVATE", "")
	t.Setenv("WEBHOOK_ALLOWED_HOSTS", "n8n.internal, automation.local")
	if err := ValidateWebhookURL("http://n8n.internal/webhook/x"); err != nil {
		t.Errorf("expected allowlisted host to pass, got %v", err)
	}
}

func TestSignBody(t *testing.T) {
	t.Setenv("WEBHOOK_SIGNING_SECRET", "")
	if got := signBody([]byte("x")); got != "" {
		t.Errorf("expected empty signature without secret, got %q", got)
	}
	t.Setenv("WEBHOOK_SIGNING_SECRET", "topsecret")
	got := signBody([]byte("hello"))
	if len(got) < len("sha256=") || got[:7] != "sha256=" {
		t.Errorf("expected sha256= prefix, got %q", got)
	}
}
