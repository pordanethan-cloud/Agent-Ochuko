package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"syscall"
	"time"

	"github.com/pordanethan-cloud/agent-ochuko/gateway/pkg/auth"
	"github.com/pordanethan-cloud/agent-ochuko/gateway/pkg/cache"
	"github.com/pordanethan-cloud/agent-ochuko/gateway/pkg/middleware"
	"github.com/pordanethan-cloud/agent-ochuko/gateway/pkg/proxy"
)

func main() {
	log.Println("==========================================================")
	log.Println(" Starting Agent Ochuko Single-Container Gateway Supervisor ")
	log.Println("==========================================================")

	pythonHost := getEnv("PYTHON_HOST", "127.0.0.1")
	pythonPort := getEnv("PYTHON_PORT", "8001")
	gatewayPort := getEnv("PORT", "8000")
	pythonTarget := fmt.Sprintf("http://%s:%s", pythonHost, pythonPort)

	// 1. Spawn Python AI Worker subprocess
	cmd := exec.Command("uvicorn", "app.main:app", "--host", pythonHost, "--port", pythonPort, "--no-access-log")
	cmd.Dir = "/app"
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	log.Printf("[SUPERVISOR] Spawning Python AI Worker on %s...", pythonTarget)
	if err := cmd.Start(); err != nil {
		log.Fatalf("[SUPERVISOR] Failed to start Python AI Worker: %v", err)
	}

	// Channel to capture Python process crashes
	pyExitChan := make(chan error, 1)
	go func() {
		pyExitChan <- cmd.Wait()
	}()

	// 2. Wait for Python worker to become ready
	log.Println("[SUPERVISOR] Waiting for Python AI Worker readiness probe...")
	if err := waitForBackendReady(pythonTarget+"/ready", 30*time.Second); err != nil {
		log.Printf("[SUPERVISOR] Warning: Python backend readiness timeout: %v", err)
	} else {
		log.Println("[SUPERVISOR] Python AI Worker is READY.")
	}

	// 3. Initialize Gateway Components
	jwtValidator := auth.NewJWTValidator()
	corsMW := middleware.NewCORSMiddleware()
	rateLimiter := middleware.NewRateLimiter(120, 1*time.Minute)
	hotCache := cache.NewHotCache(30*time.Minute, 1000)

	gatewayProxy, err := proxy.NewGatewayProxy(pythonTarget, jwtValidator, hotCache)
	if err != nil {
		log.Fatalf("[SUPERVISOR] Failed to initialize Gateway Proxy: %v", err)
	}

	// Wrap middleware chain: CORS -> RateLimiter -> Proxy Handler
	handler := corsMW.Handler(rateLimiter.Handler(gatewayProxy.Handler()))

	server := &http.Server{
		Addr:         ":" + gatewayPort,
		Handler:      handler,
		ReadTimeout:  300 * time.Second, // Long timeout for SSE streaming
		WriteTimeout: 300 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	// 4. Start Go HTTP Server in background
	go func() {
		log.Printf("[GATEWAY] Go Edge Gateway listening on 0.0.0.0:%s", gatewayPort)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("[GATEWAY] HTTP Server error: %v", err)
		}
	}()

	// 5. Signal handling for Graceful Shutdown
	stopChan := make(chan os.Signal, 1)
	signal.Notify(stopChan, os.Interrupt, syscall.SIGTERM, syscall.SIGINT)

	select {
	case sig := <-stopChan:
		log.Printf("[SUPERVISOR] Received OS signal (%v). Initiating graceful shutdown...", sig)
	case err := <-pyExitChan:
		log.Printf("[SUPERVISOR] Python worker exited unexpectedly: %v", err)
	}

	// Graceful shutdown sequence
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := server.Shutdown(ctx); err != nil {
		log.Printf("[GATEWAY] Server shutdown error: %v", err)
	}

	// Terminate Python subprocess
	if cmd.Process != nil {
		log.Println("[SUPERVISOR] Sending SIGTERM to Python worker process...")
		_ = cmd.Process.Signal(syscall.SIGTERM)
		time.Sleep(1 * time.Second)
		_ = cmd.Process.Kill()
	}

	log.Println("[SUPERVISOR] Shutdown complete. Exiting.")
}

func waitForBackendReady(targetURL string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	client := &http.Client{Timeout: 1 * time.Second}

	for time.Now().Before(deadline) {
		resp, err := client.Get(targetURL)
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				return nil
			}
		}
		time.Sleep(500 * time.Millisecond)
	}
	return fmt.Errorf("backend at %s did not become ready within %v", targetURL, timeout)
}

func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}
