package camera

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"errors"
	"fmt"
	"io"
)

type CredentialCipher struct {
	gcm cipher.AEAD
}

func NewCredentialCipher(key string) (*CredentialCipher, error) {
	// A 32-byte key is used verbatim (AES-256) for backward compatibility.
	// Any other length is derived via SHA-256 instead of the previous weak
	// zero-padding/truncation, which degraded entropy for short keys.
	k := []byte(key)
	if len(k) != 32 {
		sum := sha256.Sum256(k)
		k = sum[:]
	}
	block, err := aes.NewCipher(k)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	return &CredentialCipher{gcm: gcm}, nil
}

func (c *CredentialCipher) Encrypt(plaintext string) ([]byte, error) {
	if plaintext == "" {
		return nil, nil
	}
	nonce := make([]byte, c.gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, err
	}
	return c.gcm.Seal(nonce, nonce, []byte(plaintext), nil), nil
}

func (c *CredentialCipher) Decrypt(ciphertext []byte) (string, error) {
	if len(ciphertext) == 0 {
		return "", nil
	}
	nonceSize := c.gcm.NonceSize()
	if len(ciphertext) < nonceSize {
		return "", errors.New("ciphertext too short")
	}
	nonce, data := ciphertext[:nonceSize], ciphertext[nonceSize:]
	plain, err := c.gcm.Open(nil, nonce, data, nil)
	if err != nil {
		return "", err
	}
	return string(plain), nil
}

func BuildRTSPURL(vendor, host string, port, channel int, username, password, customPath, profile string) string {
	auth := ""
	if username != "" {
		auth = username
		if password != "" {
			auth += ":" + password
		}
		auth += "@"
	}

	switch vendor {
	case "dahua":
		subtype := "0"
		if profile == "sub" {
			subtype = "1"
		}
		return fmt.Sprintf("rtsp://%s%s:%d/cam/realmonitor?channel=%d&subtype=%s", auth, host, port, channel, subtype)
	case "hikvision":
		suffix := "01"
		if profile == "sub" {
			suffix = "02"
		}
		return fmt.Sprintf("rtsp://%s%s:%d/Streaming/Channels/%d%s", auth, host, port, channel, suffix)
	default:
		if customPath != "" {
			return fmt.Sprintf("rtsp://%s%s:%d%s", auth, host, port, customPath)
		}
		return fmt.Sprintf("rtsp://%s%s:%d/stream", auth, host, port)
	}
}
