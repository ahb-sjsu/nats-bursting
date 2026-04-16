// nats-bursting is the controller that bridges Atlas's local NATS bus
// to a remote Kubernetes cluster (e.g. NRP Nautilus). See
// https://github.com/ahb-sjsu/nats-bursting for the design.
package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/ahb-sjsu/nats-bursting/internal/config"
	"github.com/ahb-sjsu/nats-bursting/internal/natsbridge"
	"github.com/ahb-sjsu/nats-bursting/internal/submitter"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

func main() {
	configPath := flag.String("config", "", "Path to YAML config (optional)")
	natsURL := flag.String("nats", "", "NATS URL (overrides config)")
	kubeconfig := flag.String("kubeconfig", "", "Path to kubeconfig (overrides config)")
	namespace := flag.String("namespace", "", "Kubernetes namespace (overrides config)")
	logLevel := flag.String("log-level", "", "Log level: debug|info|warn|error (overrides config)")
	flag.Parse()

	cfg, err := config.Load(*configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "load config: %v\n", err)
		os.Exit(1)
	}
	if *natsURL != "" {
		cfg.NATS.URL = *natsURL
	}
	if *kubeconfig != "" {
		cfg.K8s.Kubeconfig = *kubeconfig
	}
	if *namespace != "" {
		cfg.K8s.Namespace = *namespace
	}
	if *logLevel != "" {
		cfg.LogLevel = *logLevel
	}

	log := newLogger(cfg.LogLevel)
	log.Info("nats-bursting starting",
		"nats", cfg.NATS.URL,
		"namespace", cfg.K8s.Namespace,
		"kubeconfig", cfg.K8s.Kubeconfig,
	)

	client, err := newK8sClient(cfg.K8s)
	if err != nil {
		log.Error("k8s client", "err", err)
		os.Exit(1)
	}

	sub := submitter.New(client, cfg.K8s.Namespace)
	bridge, err := natsbridge.New(cfg.NATS, sub, log)
	if err != nil {
		log.Error("nats bridge", "err", err)
		os.Exit(1)
	}
	defer bridge.Close()

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	if err := bridge.Run(ctx); err != nil {
		log.Error("bridge run", "err", err)
		os.Exit(1)
	}
	log.Info("nats-bursting stopped")
}

func newLogger(level string) *slog.Logger {
	var lvl slog.Level
	switch level {
	case "debug":
		lvl = slog.LevelDebug
	case "warn":
		lvl = slog.LevelWarn
	case "error":
		lvl = slog.LevelError
	default:
		lvl = slog.LevelInfo
	}
	return slog.New(slog.NewJSONHandler(os.Stderr, &slog.HandlerOptions{Level: lvl}))
}

func newK8sClient(c config.K8sConfig) (kubernetes.Interface, error) {
	var (
		restCfg *rest.Config
		err     error
	)
	if c.InClusterAuth {
		restCfg, err = rest.InClusterConfig()
	} else {
		path := c.Kubeconfig
		if path == "" {
			path = clientcmd.RecommendedHomeFile
		}
		restCfg, err = clientcmd.BuildConfigFromFlags("", path)
	}
	if err != nil {
		return nil, fmt.Errorf("k8s config: %w", err)
	}
	return kubernetes.NewForConfig(restCfg)
}
