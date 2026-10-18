// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Standardized dynamic version resolution for Go microservices in the
// Bastien-Antigravity ecosystem. Implements hierarchical semver resolution
// adhering to VERSION.txt as the Single Source of Truth.
//
// DATA FLOW:
// LDFLAGS BuildVersion -> Env (APP_VERSION/SERVICE_VERSION) -> Tree Climber (VERSION.txt) -> Fallback (0.0.1)
//
// KEY PARAMETERS:
// - BuildVersion: Link-time semver injected via -ldflags -X.
// - cachedVersion: In-memory atomic cache preventing redundant disk I/O.
// -----------------------------------------------------------------------------

package version

import (
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/utils"
)

// BuildVersion holds the semver injected at build time via:
// -ldflags="-X 'github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/version.BuildVersion=$(VERSION)'"
var BuildVersion string

const DefaultFallbackVersion = "0.0.1"

var (
	cachedVersion atomic.Pointer[string]
	resolveOnce   sync.Once
	testMutex     sync.Mutex
)

// -----------------------------------------------------------------------------

// Get returns the cached semantic version of the running microservice.
// It resolves the version on first call and caches the result.
func Get() string {
	if ptr := cachedVersion.Load(); ptr != nil {
		return *ptr
	}

	resolveOnce.Do(func() {
		v := Resolve()
		cachedVersion.Store(&v)
	})

	if ptr := cachedVersion.Load(); ptr != nil {
		return *ptr
	}
	return DefaultFallbackVersion
}

// -----------------------------------------------------------------------------

// Resolve performs the full hierarchical resolution without caching.
// Priority:
// 1. BuildVersion (link-time LDFLAGS injection)
// 2. Environment variables: APP_VERSION, SERVICE_VERSION
// 3. User-provided candidate paths
// 4. Upward directory climber looking for VERSION.txt from base directory
// 5. DefaultFallbackVersion ("0.0.1")
func Resolve(hints ...string) string {
	// 1. Link-time injected version
	if trimmed := strings.TrimSpace(BuildVersion); trimmed != "" {
		return trimmed
	}

	// 2. Environment variables
	for _, envKey := range []string{"APP_VERSION", "SERVICE_VERSION"} {
		if val := strings.TrimSpace(os.Getenv(envKey)); val != "" {
			return val
		}
	}

	// 3. Explicit candidate hints
	for _, hint := range hints {
		if hint == "" {
			continue
		}
		if v, ok := readVersionFile(hint); ok {
			return v
		}
	}

	// 4. Upward tree climbing starting from base directory and cwd
	startDirs := []string{utils.GetBaseDir()}
	if cwd, err := os.Getwd(); err == nil && cwd != "" {
		startDirs = append(startDirs, cwd)
	}

	for _, startDir := range startDirs {
		curr := startDir
		for i := 0; i < 12; i++ {
			candidate := filepath.Join(curr, "VERSION.txt")
			if v, ok := readVersionFile(candidate); ok {
				return v
			}

			parent := filepath.Dir(curr)
			if parent == curr || parent == "" || parent == "." {
				break
			}
			curr = parent
		}
	}

	// 5. Default fallback
	return DefaultFallbackVersion
}

// -----------------------------------------------------------------------------

// Set overrides the cached version (primarily for testing or dynamic lifecycle hooks).
func Set(v string) {
	trimmed := strings.TrimSpace(v)
	if trimmed == "" {
		trimmed = DefaultFallbackVersion
	}
	cachedVersion.Store(&trimmed)
}

// Reset clears the cached version so the next Get() will re-resolve. Primarily for testing.
func Reset() {
	testMutex.Lock()
	defer testMutex.Unlock()
	cachedVersion.Store(nil)
	resolveOnce = sync.Once{}
}

// -----------------------------------------------------------------------------

func readVersionFile(path string) (string, bool) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", false
	}
	v := strings.TrimSpace(string(data))
	if v == "" {
		return "", false
	}
	return v, true
}
