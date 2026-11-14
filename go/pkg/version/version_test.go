package version_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/version"
	"github.com/stretchr/testify/assert"
)

func TestVersionResolution(t *testing.T) {
	// Clean slate
	version.Reset()
	defer version.Reset()

	t.Run("DefaultResolutionFromRepoRoot", func(t *testing.T) {
		version.Reset()
		v := version.Get()
		assert.NotEmpty(t, v)
		assert.Equal(t, "0.0.1", v)
	})

	t.Run("TreeClimber_VERSION_txt", func(t *testing.T) {
		version.Reset()
		tmpDir := t.TempDir()
		assert.NoError(t, os.Mkdir(filepath.Join(tmpDir, ".git"), 0755))
		assert.NoError(t, os.WriteFile(filepath.Join(tmpDir, "VERSION.txt"), []byte("2.5.9\n"), 0644))
		subDir := filepath.Join(tmpDir, "src", "pkg")
		assert.NoError(t, os.MkdirAll(subDir, 0755))

		origWd, err := os.Getwd()
		assert.NoError(t, err)
		assert.NoError(t, os.Chdir(subDir))
		defer func() { _ = os.Chdir(origWd) }()

		assert.Equal(t, "2.5.9", version.Resolve())
	})

	t.Run("EnvVarsIgnored", func(t *testing.T) {
		version.Reset()
		t.Setenv("APP_VERSION", "9.9.9")
		t.Setenv("SERVICE_VERSION", "8.8.8")
		tmpDir := t.TempDir()
		assert.NoError(t, os.Mkdir(filepath.Join(tmpDir, ".git"), 0755))
		assert.NoError(t, os.WriteFile(filepath.Join(tmpDir, "VERSION.txt"), []byte("3.0.0\n"), 0644))

		origWd, err := os.Getwd()
		assert.NoError(t, err)
		assert.NoError(t, os.Chdir(tmpDir))
		defer func() { _ = os.Chdir(origWd) }()

		assert.Equal(t, "3.0.0", version.Resolve())
	})

	t.Run("ExplicitHints", func(t *testing.T) {
		version.Reset()
		tmpDir := t.TempDir()
		customVersionPath := filepath.Join(tmpDir, "custom_ver.txt")
		err := os.WriteFile(customVersionPath, []byte("9.9.9\n"), 0644)
		assert.NoError(t, err)

		v := version.Resolve(customVersionPath)
		assert.Equal(t, "9.9.9", v)
	})

	t.Run("FailFastWhenNotFound", func(t *testing.T) {
		version.Reset()
		tmpDir := t.TempDir()
		assert.NoError(t, os.Mkdir(filepath.Join(tmpDir, ".git"), 0755))

		origWd, err := os.Getwd()
		assert.NoError(t, err)
		assert.NoError(t, os.Chdir(tmpDir))
		defer func() { _ = os.Chdir(origWd) }()

		_, resolveErr := version.ResolveE(filepath.Join(tmpDir, "non_existent.txt"))
		assert.Error(t, resolveErr)
		assert.Panics(t, func() {
			version.Resolve()
		})
	})

	t.Run("CachingBehavior", func(t *testing.T) {
		version.Reset()
		tmpDir := t.TempDir()
		assert.NoError(t, os.Mkdir(filepath.Join(tmpDir, ".git"), 0755))
		verPath := filepath.Join(tmpDir, "VERSION.txt")
		assert.NoError(t, os.WriteFile(verPath, []byte("1.1.1\n"), 0644))

		origWd, err := os.Getwd()
		assert.NoError(t, err)
		assert.NoError(t, os.Chdir(tmpDir))
		defer func() { _ = os.Chdir(origWd) }()

		first := version.Get()
		assert.Equal(t, "1.1.1", first)

		// Change VERSION.txt - Get() must return cached value
		assert.NoError(t, os.WriteFile(verPath, []byte("2.2.2\n"), 0644))
		cached := version.Get()
		assert.Equal(t, "1.1.1", cached)

		// After Reset(), Get() resolves fresh value
		version.Reset()
		fresh := version.Get()
		assert.Equal(t, "2.2.2", fresh)
	})

	t.Run("SetAndGet", func(t *testing.T) {
		version.Reset()
		version.Set("7.7.7")
		assert.Equal(t, "7.7.7", version.Get())

		assert.Panics(t, func() {
			version.Set("   ")
		})
	})
}
