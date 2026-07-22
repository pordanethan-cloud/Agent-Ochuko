package cache

import (
	"crypto/sha256"
	"encoding/hex"
	"sync"
	"time"
)

type CacheItem struct {
	Value       []byte
	ContentType string
	CreatedAt   time.Time
	ExpiresAt   time.Time
}

type HotCache struct {
	mu         sync.RWMutex
	items      map[string]*CacheItem
	defaultTTL time.Duration
	maxEntries int
}

func NewHotCache(defaultTTL time.Duration, maxEntries int) *HotCache {
	hc := &HotCache{
		items:      make(map[string]*CacheItem),
		defaultTTL: defaultTTL,
		maxEntries: maxEntries,
	}

	// Periodic cleanup background worker
	go func() {
		for {
			time.Sleep(5 * time.Minute)
			hc.Cleanup()
		}
	}()

	return hc
}

// GenerateKey computes a SHA-256 hash string for user_id + prompt.
func GenerateKey(userID, prompt string) string {
	hasher := sha256.New()
	hasher.Write([]byte(userID + ":" + prompt))
	return hex.EncodeToString(hasher.Sum(nil))
}

func (hc *HotCache) Get(key string) ([]byte, string, bool) {
	hc.mu.RLock()
	defer hc.mu.RUnlock()

	item, exists := hc.items[key]
	if !exists {
		return nil, "", false
	}

	if time.Now().After(item.ExpiresAt) {
		return nil, "", false
	}

	return item.Value, item.ContentType, true
}

func (hc *HotCache) Set(key string, value []byte, contentType string, ttl time.Duration) {
	hc.mu.Lock()
	defer hc.mu.Unlock()

	if ttl <= 0 {
		ttl = hc.defaultTTL
	}

	// Evict oldest entry if max capacity reached
	if len(hc.items) >= hc.maxEntries {
		var oldestKey string
		var oldestTime time.Time = time.Now()
		for k, item := range hc.items {
			if item.CreatedAt.Before(oldestTime) {
				oldestTime = item.CreatedAt
				oldestKey = k
			}
		}
		if oldestKey != "" {
			delete(hc.items, oldestKey)
		}
	}

	now := time.Now()
	hc.items[key] = &CacheItem{
		Value:       value,
		ContentType: contentType,
		CreatedAt:   now,
		ExpiresAt:   now.Add(ttl),
	}
}

func (hc *HotCache) Cleanup() {
	hc.mu.Lock()
	defer hc.mu.Unlock()

	now := time.Now()
	for k, item := range hc.items {
		if now.After(item.ExpiresAt) {
			delete(hc.items, k)
		}
	}
}
