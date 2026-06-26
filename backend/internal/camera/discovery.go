package camera

import (
	"context"
	"fmt"
	"net"
	"sort"
	"strings"
	"sync"
	"time"
)

type DiscoveredDevice struct {
	IP        string `json:"ip"`
	Port      int    `json:"port"`
	Reachable bool   `json:"reachable"`
	RTSPPort  int    `json:"rtsp_port,omitempty"`
	HasRTSP   bool   `json:"has_rtsp,omitempty"`
}

// Common RTSP ports (554 standard + frequent vendor alternates).
var rtspScanPorts = []int{554, 8554, 10554, 5544, 7070, 8000}

func detectRTSPPort(ctx context.Context, dialer net.Dialer, addr string) int {
	for _, port := range rtspScanPorts {
		if conn, err := dialer.DialContext(ctx, "tcp", net.JoinHostPort(addr, fmt.Sprintf("%d", port))); err == nil {
			conn.Close()
			return port
		}
	}
	return 0
}

func tcpOpen(ctx context.Context, dialer net.Dialer, addr string, port int) bool {
	conn, err := dialer.DialContext(ctx, "tcp", net.JoinHostPort(addr, fmt.Sprintf("%d", port)))
	if err != nil {
		return false
	}
	conn.Close()
	return true
}

func ScanSubnet(ctx context.Context, cidr string, timeout time.Duration) ([]DiscoveredDevice, error) {
	_, ipNet, err := net.ParseCIDR(strings.TrimSpace(cidr))
	if err != nil {
		return nil, fmt.Errorf("invalid CIDR %q: %w", cidr, err)
	}

	var ips []net.IP
	for ip := ipNet.IP.Mask(ipNet.Mask); ipNet.Contains(ip); incIP(ip) {
		clone := make(net.IP, len(ip))
		copy(clone, ip)
		ips = append(ips, clone)
	}
	if len(ips) > 2 {
		ips = ips[1 : len(ips)-1]
	}

	results := make([]DiscoveredDevice, 0)
	var mu sync.Mutex
	var wg sync.WaitGroup
	sem := make(chan struct{}, 128)
	dialer := net.Dialer{Timeout: timeout}

	for _, ip := range ips {
		select {
		case <-ctx.Done():
			wg.Wait()
			return results, ctx.Err()
		default:
		}

		wg.Add(1)
		sem <- struct{}{}
		go func(addr string) {
			defer wg.Done()
			defer func() { <-sem }()

			rtspPort := detectRTSPPort(ctx, dialer, addr)
			webOpen := tcpOpen(ctx, dialer, addr, 80)
			if rtspPort == 0 && !webOpen {
				return
			}

			device := DiscoveredDevice{
				IP:        addr,
				Reachable: true,
				RTSPPort:  rtspPort,
				HasRTSP:   rtspPort > 0,
			}
			if webOpen {
				device.Port = 80
			} else if rtspPort > 0 {
				device.Port = rtspPort
			}

			mu.Lock()
			results = append(results, device)
			mu.Unlock()
		}(ip.String())
	}
	wg.Wait()
	sortDiscoveredDevices(results)
	return results, nil
}

func sortDiscoveredDevices(devices []DiscoveredDevice) {
	sort.Slice(devices, func(i, j int) bool {
		si, sj := discoverySortScore(devices[i]), discoverySortScore(devices[j])
		if si != sj {
			return si > sj
		}
		return devices[i].IP < devices[j].IP
	})
}

func discoverySortScore(d DiscoveredDevice) int {
	if d.HasRTSP || d.RTSPPort > 0 {
		return 2
	}
	return 1
}

func incIP(ip net.IP) {
	for j := len(ip) - 1; j >= 0; j-- {
		ip[j]++
		if ip[j] > 0 {
			break
		}
	}
}

type StreamTestResult struct {
	URL       string `json:"url"`
	Reachable bool   `json:"reachable"`
	VideoOK   bool   `json:"video_ok"`
	Codec     string `json:"codec,omitempty"`
	Width     int    `json:"width,omitempty"`
	Height    int    `json:"height,omitempty"`
	LatencyMS int64  `json:"latency_ms,omitempty"`
	Error     string `json:"error,omitempty"`
}

func TestStream(ctx context.Context, rtspURL string, timeout time.Duration) StreamTestResult {
	result := StreamTestResult{URL: MaskRTSP(rtspURL)}

	host, port, err := parseRTSPHostPort(rtspURL)
	if err != nil {
		result.Error = err.Error()
		return result
	}
	host = NormalizeHost(host)

	start := time.Now()
	conn, err := net.DialTimeout("tcp", net.JoinHostPort(host, port), timeout)
	if err != nil {
		result.Error = err.Error()
		return result
	}
	conn.Close()
	result.Reachable = true
	result.LatencyMS = time.Since(start).Milliseconds()

	probeCtx, cancel := context.WithTimeout(ctx, onboardProbeTimeout)
	defer cancel()
	stats, err := ProbeStreamStats(probeCtx, rtspURL)
	if err != nil {
		result.Error = err.Error()
		return result
	}
	result.VideoOK = true
	result.Codec = stats.Codec
	result.Width = stats.Width
	result.Height = stats.Height
	return result
}

func parseRTSPHostPort(url string) (host, port string, err error) {
	rest := url
	if len(rest) > 7 && rest[:7] == "rtsp://" {
		rest = rest[7:]
	}
	if at := lastIndex(rest, '@'); at >= 0 {
		rest = rest[at+1:]
	}
	slash := indexByte(rest, '/')
	if slash >= 0 {
		rest = rest[:slash]
	}
	host, port, err = net.SplitHostPort(rest)
	if err != nil {
		host = rest
		port = "554"
	}
	return host, port, nil
}

func MaskRTSP(url string) string {
	if len(url) <= 7 || url[:7] != "rtsp://" {
		return url
	}
	rest := url[7:]
	at := lastIndex(rest, '@')
	if at < 0 {
		return url
	}
	return "rtsp://***@" + rest[at+1:]
}

func lastIndex(s string, c byte) int {
	for i := len(s) - 1; i >= 0; i-- {
		if s[i] == c {
			return i
		}
	}
	return -1
}

func indexByte(s string, c byte) int {
	for i := 0; i < len(s); i++ {
		if s[i] == c {
			return i
		}
	}
	return -1
}
