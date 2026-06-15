package notify

import (
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net/smtp"
	"os"
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
		cfg.Port = 587
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

func send(cfg SMTPConfig, to, subject, body string) error {
	addr := fmt.Sprintf("%s:%d", cfg.Host, cfg.Port)
	msg := strings.Join([]string{
		fmt.Sprintf("From: %s", cfg.FromAddress),
		fmt.Sprintf("To: %s", to),
		fmt.Sprintf("Subject: %s", subject),
		"MIME-Version: 1.0",
		"Content-Type: text/plain; charset=UTF-8",
		"",
		body,
	}, "\r\n")

	auth := smtp.PlainAuth("", cfg.User, cfg.Password, cfg.Host)
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
		if _, err := w.Write([]byte(msg)); err != nil {
			return err
		}
		if err := w.Close(); err != nil {
			return err
		}
		return c.Quit()
	}
	return smtp.SendMail(addr, auth, cfg.FromAddress, []string{to}, []byte(msg))
}
