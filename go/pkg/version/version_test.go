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

	t.Run("EnvOverride_APP_VERSION", func(t *testing.T) {
		version.Reset()
		t.Setenv("APP_VERSION", "2.5.9")
		v := version.Resolve()
		assert.Equal(t, "2.5.9", v)
	})

	t.Run("EnvOverride_SERVICE_VERSION", func(t *testing.T) {
		version.Reset()
		t.Setenv("APP_VERSION", "")
		t.Setenv("SERVICE_VERSION", "3.0.0-rc1")
		v := version.Resolve()
		assert.Equal(t, "3.0.0-rc1", v)
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

	t.Run("FallbackWhenNotFound", func(t *testing.T) {
		version.Reset()
		// Temporary isolate directory
		tmpDir := t.TempDir()
		// Test hint with non-existent file
		v := version.Resolve(filepath.Join(tmpDir, "non_existent.txt"))
		// It will still climb or fallback, but if we pass an isolated dir as hint it won't crash
		assert.NotEmpty(t, v)
	})

	t.Run("CachingBehavior", func(t *testing.T) {
		version.Reset()
		t.Setenv("APP_VERSION", "1.1.1")
		first := version.Get()
		assert.Equal(t, "1.1.1", first)

		// Change env - Get() must return cached value
		t.Setenv("APP_VERSION", "2.2.2")
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
	})
}
