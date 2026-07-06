package notify

import (
	"bytes"
	"crypto/tls"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"mime/multipart"
	"net/smtp"
	"net/textproto"
	"os"
	"strconv"
	"strings"
)

type SMTPConfig struct {
	Host        string `json:"host"`
	Port        int    `json:"port"`
	User        string `json:"user"`
	Password    string `json:"password"`
	FromAddress string `json:"from_address"`
	UseTLS      bool   `json:"use_tls"`
}

func ParseSMTP(raw json.RawMessage) SMTPConfig {
	var cfg SMTPConfig
	if len(raw) > 0 {
		_ = json.Unmarshal(raw, &cfg)
	}
	if cfg.Host == "" {
		cfg.Host = os.Getenv("SMTP_HOST")
	}
	if cfg.Port == 0 {
		if p := os.Getenv("SMTP_PORT"); p != "" {
			if n, err := strconv.Atoi(p); err == nil && n > 0 {
				cfg.Port = n
			}
		}
	}
	if cfg.Port == 0 {
		host := strings.ToLower(strings.TrimSpace(cfg.Host))
		if host == "localhost" || host == "127.0.0.1" || host == "mailhog" {
			cfg.Port = 1025
		} else {
			cfg.Port = 587
		}
	}
	if !cfg.UseTLS && strings.EqualFold(os.Getenv("SMTP_USE_TLS"), "true") {
		cfg.UseTLS = true
	}
	if cfg.User == "" {
		cfg.User = os.Getenv("SMTP_USER")
	}
	if cfg.Password == "" {
		cfg.Password = os.Getenv("SMTP_PASS")
	}
	if cfg.FromAddress == "" {
		cfg.FromAddress = os.Getenv("SMTP_FROM")
	}
	if cfg.FromAddress == "" && cfg.Host != "" {
		cfg.FromAddress = "alertes@citevision.local"
	}
	return cfg
}

func SendTest(cfg SMTPConfig, to string) error {
	if cfg.Host == "" || cfg.FromAddress == "" {
		return fmt.Errorf("smtp not configured")
	}
	subject := "CitéVision — test SMTP"
	body := "Ceci est un email de test depuis CitéVision v2."
	return send(cfg, to, subject, body)
}

func SendAlert(cfg SMTPConfig, to, title, message string) error {
	return send(cfg, to, title, message)
}

// InlineImage is an image embedded in an HTML email via a cid: reference.
type InlineImage struct {
	CID         string
	ContentType string
	Data        []byte
}

// SendAlertHTML sends a premium HTML email with a plain-text fallback and optional
// inline (CID-referenced) images, using multipart/related + multipart/alternative.
func SendAlertHTML(cfg SMTPConfig, to, subject, htmlBody, textBody string, images []InlineImage) error {
	if cfg.Host == "" || cfg.FromAddress == "" {
		return fmt.Errorf("smtp not configured")
	}
	raw, err := buildMIME(cfg, to, subject, htmlBody, textBody, images)
	if err != nil {
		return err
	}
	return deliver(cfg, to, raw)
}

func buildMIME(cfg SMTPConfig, to, subject, htmlBody, textBody string, images []InlineImage) ([]byte, error) {
	var buf bytes.Buffer
	related := multipart.NewWriter(&buf)

	// Top-level headers.
	headers := []string{
		fmt.Sprintf("From: %s", cfg.FromAddress),
		fmt.Sprintf("To: %s", to),
		fmt.Sprintf("Subject: %s", encodeHeader(subject)),
		"MIME-Version: 1.0",
		fmt.Sprintf("Content-Type: multipart/related; boundary=\"%s\"", related.Boundary()),
		"",
		"",
	}
	buf.WriteString(strings.Join(headers, "\r\n"))

	// First related part: multipart/alternative (text + html).
	altHeader := make(textproto.MIMEHeader)
	altBuf := &bytes.Buffer{}
	alt := multipart.NewWriter(altBuf)
	altHeader.Set("Content-Type", fmt.Sprintf("multipart/alternative; boundary=\"%s\"", alt.Boundary()))
	altPart, err := related.CreatePart(altHeader)
	if err != nil {
		return nil, err
	}

	// Plain text alternative.
	if textBody == "" {
		textBody = "Alerte CitéVision. Activez l'affichage HTML pour voir les preuves."
	}
	tph := make(textproto.MIMEHeader)
	tph.Set("Content-Type", "text/plain; charset=UTF-8")
	tw, err := alt.CreatePart(tph)
	if err != nil {
		return nil, err
	}
	_, _ = tw.Write([]byte(textBody))

	// HTML alternative.
	hph := make(textproto.MIMEHeader)
	hph.Set("Content-Type", "text/html; charset=UTF-8")
	hw, err := alt.CreatePart(hph)
	if err != nil {
		return nil, err
	}
	_, _ = hw.Write([]byte(htmlBody))
	_ = alt.Close()
	_, _ = altPart.Write(altBuf.Bytes())

	// Inline images.
	for _, img := range images {
		if len(img.Data) == 0 {
			continue
		}
		ih := make(textproto.MIMEHeader)
		ct := img.ContentType
		if ct == "" {
			ct = "image/jpeg"
		}
		ih.Set("Content-Type", ct)
		ih.Set("Content-Transfer-Encoding", "base64")
		ih.Set("Content-ID", fmt.Sprintf("<%s>", img.CID))
		ih.Set("Content-Disposition", fmt.Sprintf("inline; filename=\"%s.jpg\"", img.CID))
		iw, err := related.CreatePart(ih)
		if err != nil {
			return nil, err
		}
		b64 := base64.StdEncoding.EncodeToString(img.Data)
		for i := 0; i < len(b64); i += 76 {
			end := i + 76
			if end > len(b64) {
				end = len(b64)
			}
			_, _ = iw.Write([]byte(b64[i:end] + "\r\n"))
		}
	}
	_ = related.Close()
	return buf.Bytes(), nil
}

func encodeHeader(s string) string {
	// RFC 2047 encoded-word for non-ASCII subjects (accents).
	for _, r := range s {
		if r > 127 {
			return "=?UTF-8?B?" + base64.StdEncoding.EncodeToString([]byte(s)) + "?="
		}
	}
	return s
}

func send(cfg SMTPConfig, to, subject, body string) error {
	msg := strings.Join([]string{
		fmt.Sprintf("From: %s", cfg.FromAddress),
		fmt.Sprintf("To: %s", to),
		fmt.Sprintf("Subject: %s", encodeHeader(subject)),
		"MIME-Version: 1.0",
		"Content-Type: text/plain; charset=UTF-8",
		"",
		body,
	}, "\r\n")
	return deliver(cfg, to, []byte(msg))
}

// deliver sends a fully-formed RFC 822 message to a single recipient.
func deliver(cfg SMTPConfig, to string, msg []byte) error {
	addr := fmt.Sprintf("%s:%d", cfg.Host, cfg.Port)
	// No AUTH for unauthenticated relays (e.g. MailHog in demo); passing a
	// non-nil auth to such a server makes net/smtp fail with "doesn't support AUTH".
	var auth smtp.Auth
	if cfg.User != "" {
		auth = smtp.PlainAuth("", cfg.User, cfg.Password, cfg.Host)
	}
	if cfg.UseTLS {
		tlsCfg := &tls.Config{ServerName: cfg.Host}
		conn, err := tls.Dial("tcp", addr, tlsCfg)
		if err != nil {
			return err
		}
		c, err := smtp.NewClient(conn, cfg.Host)
		if err != nil {
			return err
		}
		if cfg.User != "" {
			if err := c.Auth(auth); err != nil {
				return err
			}
		}
		if err := c.Mail(cfg.FromAddress); err != nil {
			return err
		}
		if err := c.Rcpt(to); err != nil {
			return err
		}
		w, err := c.Data()
		if err != nil {
			return err
		}
		if _, err := w.Write(msg); err != nil {
			return err
		}
		if err := w.Close(); err != nil {
			return err
		}
		return c.Quit()
	}
	return smtp.SendMail(addr, auth, cfg.FromAddress, []string{to}, msg)
}
