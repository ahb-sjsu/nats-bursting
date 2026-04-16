// Package submitter renders a JobDescriptor into a Kubernetes Job
// and applies it via client-go.
package submitter

import (
	"context"
	"fmt"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

// JobDescriptor is the high-level request published over NATS. Kept
// deliberately small — it should map cleanly to a single Kubernetes
// Job. Anything more exotic (DAGs, parallelism beyond a single
// completion target) should publish multiple JobDescriptors.
type JobDescriptor struct {
	Name      string            `json:"name" yaml:"name"`
	Image     string            `json:"image" yaml:"image"`
	Command   []string          `json:"command,omitempty" yaml:"command,omitempty"`
	Args      []string          `json:"args,omitempty" yaml:"args,omitempty"`
	Env       map[string]string `json:"env,omitempty" yaml:"env,omitempty"`
	Resources Resources         `json:"resources,omitempty" yaml:"resources,omitempty"`
	Labels    map[string]string `json:"labels,omitempty" yaml:"labels,omitempty"`

	// BackoffLimit is the K8s Job spec field of the same name —
	// number of in-pod retries before the Job is marked failed.
	// Defaults to 0 (fail fast).
	BackoffLimit int32 `json:"backoff_limit,omitempty" yaml:"backoff_limit,omitempty"`
}

// Resources captures CPU/memory/GPU requests & limits.
type Resources struct {
	CPU              string `json:"cpu,omitempty" yaml:"cpu,omitempty"`                             // e.g. "4"
	Memory           string `json:"memory,omitempty" yaml:"memory,omitempty"`                       // e.g. "16Gi"
	GPU              int32  `json:"gpu,omitempty" yaml:"gpu,omitempty"`                             // count, becomes nvidia.com/gpu
	EphemeralStorage string `json:"ephemeral_storage,omitempty" yaml:"ephemeral_storage,omitempty"` // e.g. "100Gi"
}

// Submitter applies JobDescriptors via client-go.
type Submitter struct {
	Client    kubernetes.Interface
	Namespace string
}

// New creates a Submitter.
func New(client kubernetes.Interface, namespace string) *Submitter {
	return &Submitter{Client: client, Namespace: namespace}
}

// Submit creates the Job and returns the resulting Kubernetes Job
// name (which will match desc.Name unless empty, in which case the
// API server generates one).
func (s *Submitter) Submit(ctx context.Context, desc JobDescriptor) (string, error) {
	job, err := desc.ToJob(s.Namespace)
	if err != nil {
		return "", err
	}
	created, err := s.Client.BatchV1().Jobs(s.Namespace).Create(ctx, job, metav1.CreateOptions{})
	if err != nil {
		return "", fmt.Errorf("create job: %w", err)
	}
	return created.Name, nil
}

// Cancel deletes the named Job. Foreground propagation so dependent
// pods are reaped too.
func (s *Submitter) Cancel(ctx context.Context, jobName string) error {
	policy := metav1.DeletePropagationForeground
	return s.Client.BatchV1().Jobs(s.Namespace).Delete(ctx, jobName, metav1.DeleteOptions{
		PropagationPolicy: &policy,
	})
}

// ToJob renders a JobDescriptor into a *batchv1.Job ready for
// kubernetes Create. Public so the runner pod can render the same
// way for round-tripping.
func (d JobDescriptor) ToJob(namespace string) (*batchv1.Job, error) {
	if d.Image == "" {
		return nil, fmt.Errorf("JobDescriptor.Image is required")
	}
	if d.Name == "" {
		return nil, fmt.Errorf("JobDescriptor.Name is required")
	}

	envVars := make([]corev1.EnvVar, 0, len(d.Env))
	for k, v := range d.Env {
		envVars = append(envVars, corev1.EnvVar{Name: k, Value: v})
	}

	requests := corev1.ResourceList{}
	limits := corev1.ResourceList{}
	if d.Resources.CPU != "" {
		q := resource.MustParse(d.Resources.CPU)
		requests[corev1.ResourceCPU] = q
		limits[corev1.ResourceCPU] = q
	}
	if d.Resources.Memory != "" {
		q := resource.MustParse(d.Resources.Memory)
		requests[corev1.ResourceMemory] = q
		limits[corev1.ResourceMemory] = q
	}
	if d.Resources.EphemeralStorage != "" {
		q := resource.MustParse(d.Resources.EphemeralStorage)
		requests[corev1.ResourceEphemeralStorage] = q
		limits[corev1.ResourceEphemeralStorage] = q
	}
	if d.Resources.GPU > 0 {
		// nvidia.com/gpu is only valid as a limit.
		limits[corev1.ResourceName("nvidia.com/gpu")] = *resource.NewQuantity(int64(d.Resources.GPU), resource.DecimalSI)
	}

	labels := map[string]string{"app.kubernetes.io/managed-by": "nats-bursting"}
	for k, v := range d.Labels {
		labels[k] = v
	}

	backoff := d.BackoffLimit
	job := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      d.Name,
			Namespace: namespace,
			Labels:    labels,
		},
		Spec: batchv1.JobSpec{
			BackoffLimit: &backoff,
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{Labels: labels},
				Spec: corev1.PodSpec{
					RestartPolicy: corev1.RestartPolicyNever,
					Containers: []corev1.Container{{
						Name:    "main",
						Image:   d.Image,
						Command: d.Command,
						Args:    d.Args,
						Env:     envVars,
						Resources: corev1.ResourceRequirements{
							Requests: requests,
							Limits:   limits,
						},
					}},
				},
			},
		},
	}
	return job, nil
}
