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

	// NodeSelector constrains scheduling to nodes matching these labels,
	// e.g. {"nvidia.com/gpu.product": "NVIDIA-A10"} to avoid reserved GPU
	// types. Rendered into the pod template's nodeSelector.
	NodeSelector map[string]string `json:"node_selector,omitempty" yaml:"node_selector,omitempty"`

	// BackoffLimit is the K8s Job spec field of the same name —
	// number of in-pod retries before the Job is marked failed.
	// Defaults to 0 (fail fast).
	BackoffLimit int32 `json:"backoff_limit,omitempty" yaml:"backoff_limit,omitempty"`

	// Volumes attach storage to the container. Without these, any
	// workload holding state on a PVC (a built index, a shared basis)
	// had to bypass burst.submit and hand-apply a manifest, which also
	// bypassed the politeness backoff and the dashboard labels.
	Volumes []Volume `json:"volumes,omitempty" yaml:"volumes,omitempty"`
}

// Volume attaches one storage source to the job's container. Exactly one
// of ClaimName or ConfigMap must be set. This deliberately covers only
// the two sources cluster workloads here actually use — PVCs for data,
// ConfigMaps for code — rather than mirroring the whole corev1.Volume
// union, which would make the descriptor a second Kubernetes API.
type Volume struct {
	Name      string `json:"name" yaml:"name"`
	MountPath string `json:"mount_path" yaml:"mount_path"`
	ReadOnly  bool   `json:"read_only,omitempty" yaml:"read_only,omitempty"`

	ClaimName string `json:"claim_name,omitempty" yaml:"claim_name,omitempty"`
	ConfigMap string `json:"config_map,omitempty" yaml:"config_map,omitempty"`
}

// validate returns an error describing why the volume cannot be rendered.
func (v Volume) validate() error {
	if v.Name == "" {
		return fmt.Errorf("volume: Name is required")
	}
	if v.MountPath == "" {
		return fmt.Errorf("volume %q: MountPath is required", v.Name)
	}
	switch {
	case v.ClaimName != "" && v.ConfigMap != "":
		return fmt.Errorf("volume %q: set exactly one of ClaimName or ConfigMap, not both", v.Name)
	case v.ClaimName == "" && v.ConfigMap == "":
		return fmt.Errorf("volume %q: one of ClaimName or ConfigMap is required", v.Name)
	}
	return nil
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

	vols := make([]corev1.Volume, 0, len(d.Volumes))
	mounts := make([]corev1.VolumeMount, 0, len(d.Volumes))
	seen := make(map[string]bool, len(d.Volumes))
	for _, v := range d.Volumes {
		if err := v.validate(); err != nil {
			return nil, err
		}
		if seen[v.Name] {
			return nil, fmt.Errorf("volume %q: duplicate name", v.Name)
		}
		seen[v.Name] = true

		vol := corev1.Volume{Name: v.Name}
		if v.ClaimName != "" {
			vol.VolumeSource = corev1.VolumeSource{
				PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{
					ClaimName: v.ClaimName,
					ReadOnly:  v.ReadOnly,
				},
			}
		} else {
			vol.VolumeSource = corev1.VolumeSource{
				ConfigMap: &corev1.ConfigMapVolumeSource{
					LocalObjectReference: corev1.LocalObjectReference{Name: v.ConfigMap},
				},
			}
		}
		vols = append(vols, vol)
		mounts = append(mounts, corev1.VolumeMount{
			Name:      v.Name,
			MountPath: v.MountPath,
			ReadOnly:  v.ReadOnly,
		})
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
					NodeSelector:  d.NodeSelector,
					Volumes:       vols,
					Containers: []corev1.Container{{
						Name:         "main",
						Image:        d.Image,
						Command:      d.Command,
						Args:         d.Args,
						Env:          envVars,
						VolumeMounts: mounts,
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
