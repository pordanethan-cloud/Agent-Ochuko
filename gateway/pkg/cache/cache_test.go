package cache

import (
	"bytes"
	"testing"
	"time"
)

func TestHotCacheGetSet(t *testing.T) {
	hc := NewHotCache(30*time.Minute, 100)
	key := GenerateKey("user123", "Explain system architecture")

	val, contentType, ok := hc.Get(key)
	if ok {
		t.Fatalf("Expected cache miss for new key, got hit")
	}

	expectedVal := []byte("Agent Ochuko uses a single-container Go Edge Gateway.")
	expectedCT := "application/json"
	hc.Set(key, expectedVal, expectedCT, 30*time.Minute)

	val, contentType, ok = hc.Get(key)
	if !ok {
		t.Fatalf("Expected cache hit, got miss")
	}
	if !bytes.Equal(val, expectedVal) {
		t.Errorf("Value mismatch. Expected %s, got %s", expectedVal, val)
	}
	if contentType != expectedCT {
		t.Errorf("ContentType mismatch. Expected %s, got %s", expectedCT, contentType)
	}
}

func TestHotCacheTTLExpiration(t *testing.T) {
	hc := NewHotCache(50*time.Millisecond, 100)
	key := GenerateKey("user456", "Quick question")

	hc.Set(key, []byte("quick answer"), "text/plain", 50*time.Millisecond)

	_, _, ok := hc.Get(key)
	if !ok {
		t.Fatalf("Expected cache hit before expiration")
	}

	time.Sleep(100 * time.Millisecond)

	_, _, ok = hc.Get(key)
	if ok {
		t.Fatalf("Expected cache miss after expiration")
	}
}

func TestHotCacheMaxEntriesEviction(t *testing.T) {
	hc := NewHotCache(30*time.Minute, 2)

	hc.Set("k1", []byte("v1"), "text/plain", 30*time.Minute)
	time.Sleep(5 * time.Millisecond)
	hc.Set("k2", []byte("v2"), "text/plain", 30*time.Minute)
	time.Sleep(5 * time.Millisecond)
	hc.Set("k3", []byte("v3"), "text/plain", 30*time.Minute)

	_, _, ok1 := hc.Get("k1")
	if ok1 {
		t.Errorf("Expected k1 to be evicted due to max capacity")
	}

	_, _, ok3 := hc.Get("k3")
	if !ok3 {
		t.Errorf("Expected k3 to be in cache")
	}
}
