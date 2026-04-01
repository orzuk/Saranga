#!/bin/bash
# Quick test: is the vLLM server running and responding?
# Usage: bash test_vllm_server.sh [URL]

URL="${1:-${LLM_API_URL:-http://localhost:8000}}"

echo "Testing vLLM server at: $URL"
echo ""

# 1. Check if server is reachable
echo "--- Health check ---"
curl -s --max-time 5 "$URL/health" && echo " OK" || echo " FAILED (server not reachable)"
echo ""

# 2. List available models
echo "--- Available models ---"
curl -s --max-time 5 "$URL/v1/models" | python3 -m json.tool 2>/dev/null || echo "Could not list models"
echo ""

# 3. Quick inference test
echo "--- Inference test ---"
curl -s --max-time 60 "$URL/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "meta-llama/Llama-3.1-8B-Instruct",
        "messages": [{"role": "user", "content": "What is SVD? One sentence."}],
        "max_tokens": 100,
        "temperature": 0.0
    }' | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['choices'][0]['message']['content'])" 2>/dev/null \
    || echo "Inference failed"
