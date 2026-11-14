// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Standardized dynamic version resolution for Go microservices in the
// Bastien-Antigravity ecosystem. Implements hierarchical semver resolution
// adhering to VERSION.txt as the Single Source of Truth.
//
// DATA FLOW:
// Explicit Hints -> Tree Climber (VERSION.txt) -> BuildVersion (from VERSION.txt via LDFLAGS) -> Panic (FAIL-FAST)
//
// KEY PARAMETERS:
// - BuildVersion: Link-time semver injected via -ldflags -X.
// - cachedVersion: In-memory atomic cache preventing redundant disk I/O.
// -----------------------------------------------------------------------------

package version

import (
	"fmt"
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

var (
	cachedVersion atomic.Pointer[string]
	resolveMutex  sync.Mutex
)

// -----------------------------------------------------------------------------

// Get returns the cached semantic version of the running microservice.
// It resolves the version on first call, caches the result, and panics fail-fast if unresolved.
func Get() string {
	if ptr := cachedVersion.Load(); ptr != nil {
		return *ptr
	}

	resolveMutex.Lock()
	defer resolveMutex.Unlock()

	if ptr := cachedVersion.Load(); ptr != nil {
		return *ptr
	}

	v := Resolve()
	cachedVersion.Store(&v)
	return v
}

// -----------------------------------------------------------------------------

// Resolve performs the full hierarchical resolution without caching and panics fail-fast if unresolved.
// Priority:
// 1. User-provided candidate VERSION.txt paths
// 2. Upward directory climber looking for VERSION.txt from base directory and cwd
// 3. BuildVersion (link-time LDFLAGS baked from VERSION.txt in release binaries)
func Resolve(hints ...string) string {
	v, err := ResolveE(hints...)
	if err != nil {
		panic(err)
	}
	return v
}

// ResolveE performs VERSION.txt resolution without caching and returns an error if VERSION.txt is absent.
func ResolveE(hints ...string) (string, error) {
	// 1. Explicit candidate hints
	for _, hint := range hints {
		if hint == "" {
			continue
		}
		if v, ok := readVersionFile(hint); ok {
			return v, nil
		}
	}

	// 2. Upward tree climbing starting from base directory and cwd
	startDirs := []string{utils.GetBaseDir()}
	if cwd, err := os.Getwd(); err == nil && cwd != "" {
		startDirs = append(startDirs, cwd)
	}

	for _, startDir := range startDirs {
		curr := startDir
		for i := 0; i < 12; i++ {
			candidate := filepath.Join(curr, "VERSION.txt")
			if v, ok := readVersionFile(candidate); ok {
				return v, nil
			}

			if _, gitErr := os.Stat(filepath.Join(curr, ".git")); gitErr == nil {
				break
			}

			parent := filepath.Dir(curr)
			if parent == curr || parent == "" || parent == "." {
				break
			}
			curr = parent
		}
	}

	// 3. Link-time injected version (populated from VERSION.txt via Makefile/Dockerfile)
	if trimmed := strings.TrimSpace(BuildVersion); trimmed != "" {
		return trimmed, nil
	}

	return "", fmt.Errorf("version.Resolve: VERSION.txt not found or empty (FAIL-FAST)")
}

// -----------------------------------------------------------------------------

// Set overrides the cached version (primarily for testing or dynamic lifecycle hooks).
// Fails fast on empty input.
func Set(v string) {
	trimmed := strings.TrimSpace(v)
	if trimmed == "" {
		panic("version.Set: version string must not be empty (FAIL-FAST)")
	}
	cachedVersion.Store(&trimmed)
}

// Reset clears the cached version so the next Get() will re-resolve. Primarily for testing.
func Reset() {
	resolveMutex.Lock()
	defer resolveMutex.Unlock()
	cachedVersion.Store(nil)
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
