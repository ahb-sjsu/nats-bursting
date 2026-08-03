package submitter

import (
	"context"
	"testing"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/client-go/kubernetes/fake"
)

func TestToJobMissingImageErrors(t *testing.T) {
	_, err := JobDescriptor{Name: "x"}.ToJob("ns")
	if err == nil {
		t.Fatal("want error for missing image")
	}
}

func TestToJobMissingNameErrors(t *testing.T) {
	_, err := JobDescriptor{Image: "alpine"}.ToJob("ns")
	if err == nil {
		t.Fatal("want error for missing name")
	}
}

func TestToJobRendersResources(t *testing.T) {
	d := JobDescriptor{
		Name:  "trainer",
		Image: "ghcr.io/example/trainer:1.0",
		Resources: Resources{
			CPU:              "4",
			Memory:           "16Gi",
			GPU:              2,
			EphemeralStorage: "200Gi",
		},
		Env: map[string]string{"FOO": "bar"},
	}
	job, err := d.ToJob("mine")
	if err != nil {
		t.Fatalf("ToJob: %v", err)
	}
	if got := job.Namespace; got != "mine" {
		t.Errorf("namespace: want mine, got %q", got)
	}
	if len(job.Spec.Template.Spec.Containers) != 1 {
		t.Fatalf("want 1 container, got %d", len(job.Spec.Template.Spec.Containers))
	}
	c := job.Spec.Template.Spec.Containers[0]
	if c.Image != d.Image {
		t.Errorf("image: want %q, got %q", d.Image, c.Image)
	}
	if _, ok := c.Resources.Limits[corev1.ResourceCPU]; !ok {
		t.Error("missing CPU limit")
	}
	if _, ok := c.Resources.Limits["nvidia.com/gpu"]; !ok {
		t.Error("missing GPU limit")
	}
	if _, ok := c.Resources.Limits[corev1.ResourceEphemeralStorage]; !ok {
		t.Error("missing ephemeral-storage limit")
	}
	if len(c.Env) != 1 || c.Env[0].Name != "FOO" || c.Env[0].Value != "bar" {
		t.Errorf("env not propagated: %+v", c.Env)
	}
}

func TestSubmitCreatesJob(t *testing.T) {
	client := fake.NewSimpleClientset()
	s := New(client, "mine")
	name, err := s.Submit(context.Background(), JobDescriptor{
		Name:  "trainer",
		Image: "alpine:3",
	})
	if err != nil {
		t.Fatalf("Submit: %v", err)
	}
	if name != "trainer" {
		t.Errorf("name: want trainer, got %q", name)
	}
}

func TestCancelDeletesJob(t *testing.T) {
	client := fake.NewSimpleClientset()
	s := New(client, "mine")
	if _, err := s.Submit(context.Background(), JobDescriptor{
		Name:  "doomed",
		Image: "alpine:3",
	}); err != nil {
		t.Fatal(err)
	}
	if err := s.Cancel(context.Background(), "doomed"); err != nil {
		t.Fatalf("Cancel: %v", err)
	}
}

func TestToJobRendersVolumes(t *testing.T) {
	d := JobDescriptor{
		Name:  "fleet-build-0",
		Image: "python:3.12",
		Volumes: []Volume{
			{Name: "idx", MountPath: "/idx", ClaimName: "tqp-fleet-10b-0"},
			{Name: "shared", MountPath: "/shared", ClaimName: "tqp-fleet-shared"},
			{Name: "code", MountPath: "/work", ConfigMap: "tqp-fleet-code", ReadOnly: true},
		},
	}
	job, err := d.ToJob("ns")
	if err != nil {
		t.Fatalf("ToJob: %v", err)
	}
	spec := job.Spec.Template.Spec
	if len(spec.Volumes) != 3 || len(spec.Containers[0].VolumeMounts) != 3 {
		t.Fatalf("want 3 volumes and 3 mounts, got %d and %d",
			len(spec.Volumes), len(spec.Containers[0].VolumeMounts))
	}
	if spec.Volumes[0].PersistentVolumeClaim == nil ||
		spec.Volumes[0].PersistentVolumeClaim.ClaimName != "tqp-fleet-10b-0" {
		t.Errorf("volume 0 should be the PVC tqp-fleet-10b-0")
	}
	if spec.Volumes[2].ConfigMap == nil || spec.Volumes[2].ConfigMap.Name != "tqp-fleet-code" {
		t.Errorf("volume 2 should be the ConfigMap tqp-fleet-code")
	}
	if spec.Containers[0].VolumeMounts[0].MountPath != "/idx" {
		t.Errorf("mount 0 path = %q, want /idx", spec.Containers[0].VolumeMounts[0].MountPath)
	}
	if !spec.Containers[0].VolumeMounts[2].ReadOnly {
		t.Errorf("mount 2 should be read-only")
	}
}

func TestToJobRejectsBadVolumes(t *testing.T) {
	cases := map[string]Volume{
		"no name":     {MountPath: "/x", ClaimName: "c"},
		"no path":     {Name: "v", ClaimName: "c"},
		"no source":   {Name: "v", MountPath: "/x"},
		"two sources": {Name: "v", MountPath: "/x", ClaimName: "c", ConfigMap: "m"},
	}
	for label, v := range cases {
		_, err := JobDescriptor{Name: "n", Image: "i", Volumes: []Volume{v}}.ToJob("ns")
		if err == nil {
			t.Errorf("%s: want error, got none", label)
		}
	}
	_, err := JobDescriptor{Name: "n", Image: "i", Volumes: []Volume{
		{Name: "dup", MountPath: "/a", ClaimName: "c"},
		{Name: "dup", MountPath: "/b", ClaimName: "c"},
	}}.ToJob("ns")
	if err == nil {
		t.Error("duplicate volume name: want error, got none")
	}
}
