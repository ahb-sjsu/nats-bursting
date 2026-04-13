// Package config holds runtime configuration for the atlas-burst
// controller. Populated from CLI flags first, environment variables
// second, optional YAML file third (precedence in that order).
package config

import (
	"fmt"
	"os"
	"time"

	"gopkg.in/yaml.v3"
)

// Config is the full runtime configuration. Pointers are used for
// optional knobs so we can distinguish "unset" from "zero".
type Config struct {
	NATS NATSConfig `yaml:"nats"`
	K8s  K8sConfig  `yaml:"k8s"`

	Politeness Politeness `yaml:"politeness"`

	// LogLevel is "debug" | "info" | "warn" | "error". Default "info".
	LogLevel string `yaml:"log_level"`
}

// NATSConfig describes how to reach the Atlas NATS server.
type NATSConfig struct {
	URL          string        `yaml:"url"`
	CredsFile    string        `yaml:"creds_file"`
	SubmitSubj   string        `yaml:"submit_subject"`
	StatusPrefix string        `yaml:"status_prefix"`
	ResultPrefix string        `yaml:"result_prefix"`
	ConnectWait  time.Duration `yaml:"connect_wait"`
}

// K8sConfig describes how to talk to the target Kubernetes cluster.
type K8sConfig struct {
	Kubeconfig string `yaml:"kubeconfig"`
	Namespace  string `yaml:"namespace"`

	// InClusterAuth, when true, uses the pod's service-account token
	// instead of a kubeconfig file. Used when atlas-burst itself runs
	// inside the target cluster.
	InClusterAuth bool `yaml:"in_cluster_auth"`
}

// Politeness mirrors polite-submit's thresholds.
type Politeness struct {
	MaxConcurrentJobs    int     `yaml:"max_concurrent_jobs"`
	MaxPendingJobs       int     `yaml:"max_pending_jobs"`
	QueueDepthThreshold  int     `yaml:"queue_depth_threshold"`
	UtilizationThreshold float64 `yaml:"utilization_threshold"`

	InitialBackoff    time.Duration `yaml:"initial_backoff"`
	MaxBackoff        time.Duration `yaml:"max_backoff"`
	BackoffMultiplier float64       `yaml:"backoff_multiplier"`
	MaxAttempts       int           `yaml:"max_attempts"`
}

// Defaults returns a Config with sensible production defaults
// suitable for NRP Nautilus.
func Defaults() Config {
	return Config{
		NATS: NATSConfig{
			URL:          "nats://localhost:4222",
			SubmitSubj:   "burst.submit",
			StatusPrefix: "burst.status",
			ResultPrefix: "burst.result",
			ConnectWait:  10 * time.Second,
		},
		K8s: K8sConfig{
			Namespace: "default",
		},
		Politeness: Politeness{
			MaxConcurrentJobs:    50,
			MaxPendingJobs:       20,
			QueueDepthThreshold:  200,
			UtilizationThreshold: 0.90,
			InitialBackoff:       30 * time.Second,
			MaxBackoff:           30 * time.Minute,
			BackoffMultiplier:    2.0,
			MaxAttempts:          20,
		},
		LogLevel: "info",
	}
}

// Load reads a YAML config file and merges it onto Defaults().
// Returns Defaults() unchanged if path is "".
func Load(path string) (Config, error) {
	cfg := Defaults()
	if path == "" {
		return cfg, nil
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return cfg, fmt.Errorf("read config %q: %w", path, err)
	}
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return cfg, fmt.Errorf("parse config %q: %w", path, err)
	}
	return cfg, nil
}
