package camera

import (
	"context"
	"fmt"
	"net"
	"sync"
	"time"
)

type DiscoveredDevice struct {
	IP        string `json:"ip"`
	Port      int    `json:"port"`
	Reachable bool   `json:"reachable"`
	RTSPPort  int    `json:"rtsp_port,omitempty"`
}

func ScanSubnet(ctx context.Context, cidr string, timeout time.Duration) ([]DiscoveredDevice, error) {
	_, ipNet, err := net.ParseCIDR(cidr)
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
	sem := make(chan struct{}, 64)

	for _, ip := range ips {
		select {
		case <-ctx.Done():
			return results, ctx.Err()
		default:
		}

		wg.Add(1)
		sem <- struct{}{}
		go func(addr string) {
			defer wg.Done()
			defer func() { <-sem }()

			device := DiscoveredDevice{IP: addr, Port: 80}
			conn, err := net.DialTimeout("tcp", net.JoinHostPort(addr, "80"), timeout)
			if err == nil {
				conn.Close()
				device.Reachable = true
			}
			rtspConn, err := net.DialTimeout("tcp", net.JoinHostPort(addr, "554"), timeout)
			if err == nil {
				rtspConn.Close()
				device.RTSPPort = 554
				device.Reachable = true
			}
			if device.Reachable {
				mu.Lock()
				results = append(results, device)
				mu.Unlock()
			}
		}(ip.String())
	}
	wg.Wait()
	return results, nil
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

	start := time.Now()
	conn, err := net.DialTimeout("tcp", net.JoinHostPort(host, port), timeout)
	if err != nil {
		result.Error = err.Error()
		return result
	}
	conn.Close()
	result.Reachable = true
	result.LatencyMS = time.Since(start).Milliseconds()
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
