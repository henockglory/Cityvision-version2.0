package frigate

import (
	"fmt"
	"log/slog"
	"os"
	"strings"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
)

// DetectGate publishes Frigate detect/set + enabled/set MQTT commands (retain=true
// so a Frigate reload cannot revive idle demo cameras from YAML detect.enabled).
type DetectGate struct {
	Broker string
	log    *slog.Logger
}

func NewDetectGate(log *slog.Logger) *DetectGate {
	if log == nil {
		log = slog.Default()
	}
	host := strings.TrimSpace(os.Getenv("MQTT_HOST"))
	if host == "" {
		host = "127.0.0.1"
	}
	port := strings.TrimSpace(os.Getenv("MQTT_PORT"))
	if port == "" {
		port = "1884"
	}
	broker := strings.TrimSpace(os.Getenv("MQTT_BROKER"))
	if broker == "" {
		broker = fmt.Sprintf("tcp://%s:%s", host, port)
	}
	return &DetectGate{Broker: broker, log: log}
}

func (g *DetectGate) connect() (mqtt.Client, error) {
	opts := mqtt.NewClientOptions().
		AddBroker(g.Broker).
		SetClientID(fmt.Sprintf("cv-detect-gate-%d", time.Now().UnixNano()%1_000_000)).
		SetConnectTimeout(3 * time.Second).
		SetAutoReconnect(false)
	cli := mqtt.NewClient(opts)
	tok := cli.Connect()
	if !tok.WaitTimeout(5 * time.Second) {
		return nil, fmt.Errorf("mqtt connect timeout")
	}
	if err := tok.Error(); err != nil {
		return nil, err
	}
	return cli, nil
}

func publishCameraState(cli mqtt.Client, frigateCamID string, kind string, on bool, retain bool) error {
	name := frigateCamID
	if !strings.HasPrefix(name, "cv_") {
		name = CameraID(name)
	}
	payload := "OFF"
	if on {
		payload = "ON"
	}
	topic := fmt.Sprintf("frigate/%s/%s/set", name, kind)
	tok := cli.Publish(topic, 1, retain, payload)
	if !tok.WaitTimeout(2 * time.Second) {
		return fmt.Errorf("publish timeout %s", topic)
	}
	return tok.Error()
}

func publishDetect(cli mqtt.Client, frigateCamID string, on bool, retain bool) error {
	return publishCameraState(cli, frigateCamID, "detect", on, retain)
}

// BoostKeepCamera turns detect OFF on otherCams and ON on keepCameraID (retain=true).
func (g *DetectGate) BoostKeepCamera(keepCameraID string, otherCameraIDs []string) error {
	keepCameraID = strings.TrimSpace(keepCameraID)
	if keepCameraID == "" {
		return fmt.Errorf("keep camera required")
	}
	cli, err := g.connect()
	if err != nil {
		return err
	}
	defer cli.Disconnect(250)

	keep := CameraID(keepCameraID)
	for _, cid := range otherCameraIDs {
		cid = strings.TrimSpace(cid)
		if cid == "" {
			continue
		}
		other := CameraID(cid)
		if other == keep {
			continue
		}
		if err := publishDetect(cli, other, false, true); err != nil {
			g.log.Warn("detect gate off failed", "camera", other, "error", err)
		}
		// Fully disable the camera: detect OFF alone keeps ffmpeg decoding
		// (12 demo cams pinned Frigate at ~676% CPU, starving the active rule).
		if err := publishCameraState(cli, other, "enabled", false, true); err != nil {
			g.log.Warn("camera disable failed", "camera", other, "error", err)
		}
	}
	if err := publishCameraState(cli, keep, "enabled", true, true); err != nil {
		g.log.Warn("camera enable failed", "camera", keep, "error", err)
	}
	if err := publishDetect(cli, keep, true, true); err != nil {
		return err
	}
	g.log.Info("frigate detect boost", "keep", keep, "others_off", len(otherCameraIDs))
	return nil
}

// AlignPower publishes enabled+detect ON for cameras with enabled rules and
// OFF for the rest, so Frigate only decodes streams that serve an active rule.
func (g *DetectGate) AlignPower(onCameraIDs, offCameraIDs []string) error {
	cli, err := g.connect()
	if err != nil {
		return err
	}
	defer cli.Disconnect(250)
	for _, cid := range offCameraIDs {
		cid = strings.TrimSpace(cid)
		if cid == "" {
			continue
		}
		_ = publishDetect(cli, cid, false, true)
		_ = publishCameraState(cli, cid, "enabled", false, true)
	}
	for _, cid := range onCameraIDs {
		cid = strings.TrimSpace(cid)
		if cid == "" {
			continue
		}
		_ = publishCameraState(cli, cid, "enabled", true, true)
		_ = publishDetect(cli, cid, true, true)
	}
	g.log.Info("frigate camera power align", "on", len(onCameraIDs), "off", len(offCameraIDs))
	return nil
}

// ClearRetainedDetect clears retained detect/set + enabled/set ghosts.
// It does NOT force ON: the compiled config (detect only where a rule is
// enabled) must stay authoritative, otherwise every demo camera burns CPU.
func (g *DetectGate) ClearRetainedDetect(cameraIDs []string) error {
	cli, err := g.connect()
	if err != nil {
		return err
	}
	defer cli.Disconnect(250)
	for _, cid := range cameraIDs {
		cid = strings.TrimSpace(cid)
		if cid == "" {
			continue
		}
		name := CameraID(cid)
		for _, kind := range []string{"detect", "enabled"} {
			topic := fmt.Sprintf("frigate/%s/%s/set", name, kind)
			tok := cli.Publish(topic, 1, true, []byte{})
			tok.WaitTimeout(2 * time.Second)
		}
	}
	return nil
}
