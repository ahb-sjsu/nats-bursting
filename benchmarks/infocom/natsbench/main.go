// natsbench: a Go request/reply driver for the nats-bursting warm-pool throughput
// arm. Drives the same Python GPU workers as bench_nats_pool.py, but from Go with
// the native nats.go client -- eliminating the single-client Python asyncio
// bottleneck so the measured throughput reflects the fabric, not the harness.
//
//	natsbench --url nats://127.0.0.1:4300 --workers 4 --task embed --batch 64 \
//	          --nreq 400 --concurrency 64 --out /tmp/e9/gonats.json
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	"github.com/nats-io/nats.go"
)

func pctl(xs []float64, p float64) float64 {
	if len(xs) == 0 {
		return 0
	}
	s := append([]float64(nil), xs...)
	sort.Float64s(s)
	return s[int(p/100*float64(len(s)-1))]
}

func main() {
	url := flag.String("url", nats.DefaultURL, "")
	workers := flag.Int("workers", 4, "")
	task := flag.String("task", "embed", "")
	batch := flag.Int("batch", 64, "")
	nreq := flag.Int("nreq", 400, "")
	conc := flag.Int("concurrency", 64, "")
	ntiny := flag.Int("ntiny", 40, "")
	out := flag.String("out", "", "")
	flag.Parse()

	nc, err := nats.Connect(*url)
	if err != nil {
		panic(err)
	}
	defer nc.Close()

	// wait for W workers to signal ready
	var ready int32
	sub, _ := nc.Subscribe("ready", func(m *nats.Msg) { atomic.AddInt32(&ready, 1) })
	t0 := time.Now()
	for atomic.LoadInt32(&ready) < int32(*workers) && time.Since(t0) < 180*time.Second {
		time.Sleep(100 * time.Millisecond)
	}
	sub.Unsubscribe()
	setup := time.Since(t0).Seconds()

	payload := []byte("tiny")
	if *task == "embed" {
		payload = []byte(fmt.Sprintf("embed:%d", *batch))
	}

	// dispatch latency: sequential round-trips
	var lat []float64
	for i := 0; i < *ntiny; i++ {
		s := time.Now()
		nc.Request("task", []byte("tiny"), 10*time.Second)
		lat = append(lat, float64(time.Since(s).Microseconds())/1000)
	}

	// throughput: bounded-concurrency fan-out
	sem := make(chan struct{}, *conc)
	var wg sync.WaitGroup
	var mu sync.Mutex
	var units int64
	var rlat []float64
	t := time.Now()
	for i := 0; i < *nreq; i++ {
		wg.Add(1)
		sem <- struct{}{}
		go func() {
			defer wg.Done()
			defer func() { <-sem }()
			s := time.Now()
			msg, err := nc.Request("task", payload, 60*time.Second)
			if err != nil {
				return
			}
			d := float64(time.Since(s).Microseconds()) / 1000
			n := 1
			if *task == "embed" {
				fmt.Sscanf(string(msg.Data), "%d", &n)
			}
			mu.Lock()
			units += int64(n)
			rlat = append(rlat, d)
			mu.Unlock()
		}()
	}
	wg.Wait()
	dt := time.Since(t).Seconds()

	res := map[string]any{
		"framework": "nats-bursting-go", "task": *task, "workers": *workers,
		"concurrency": *conc, "setup_s": setup,
		"dispatch_p50_ms": pctl(lat, 50), "dispatch_p99_ms": pctl(lat, 99),
		"throughput_req_s":  float64(*nreq) / dt,
		"throughput_docs_s": float64(units) / dt,
		"loaded_req_p50_ms": pctl(rlat, 50), "loaded_req_p99_ms": pctl(rlat, 99),
	}
	if *out != "" {
		b, _ := json.MarshalIndent(res, "", "  ")
		os.WriteFile(*out, b, 0644)
	}
	fmt.Printf("[gonats] %s W=%d conc=%d: disp p50=%.2fms | thr=%.0f req/s (%.0f docs/s) | loaded p50=%.1f p99=%.1f\n",
		*task, *workers, *conc, pctl(lat, 50), float64(*nreq)/dt, float64(units)/dt, pctl(rlat, 50), pctl(rlat, 99))
}
