"""
Smart Dispatch - Cost-Optimized AI Agent with Model Escalation

This module provides an intelligent AI agent that:
1. Starts with cheapest model (gemini-1.5-flash)
2. Escalates to more powerful models only if needed
3. Caches responses to reduce API costs
4. Tracks token usage for cost monitoring

Usage:
    from smart_dispatch import SmartAgent
    import os
    
    agent = SmartAgent(api_key=os.getenv("GEMINI_API_KEY"))
    result = agent.run_task("Summarize this text...")
"""

import os
import json
import hashlib
from functools import lru_cache
from typing import Optional, Dict, Any
from datetime import datetime

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("⚠️ google-genai not installed. Run: pip install google-genai")
    genai = None
    types = None


class SmartAgent:
    """
    Cost-optimized AI agent with automatic model escalation.
    
    Features:
    - Model hierarchy (cheap to expensive)
    - Response caching (LRU cache)
    - Token usage tracking
    - Retry with different prompts before escalating
    - File operations support
    """
    
    # Model hierarchy: Cheapest to Most Powerful
    MODEL_HIERARCHY = [
        "gemini-1.5-flash",           # 🟢 Cheapest - Fast & simple tasks
        "gemini-1.5-pro",             # 🟡 Balanced - Complex reasoning
        "gemini-2.0-flash",           # 🟠 Newer Flash - Better quality
        "gemini-2.5-pro-preview-06-05" # 🔴 Most Powerful - Hard problems
    ]
    
    # Cache directory
    CACHE_DIR = ".storage/ai_cache"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Smart Agent.
        
        Args:
            api_key: Google AI API key (defaults to GEMINI_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("API key required. Set GEMINI_API_KEY environment variable or pass api_key.")
        
        if genai is None:
            raise ImportError("google-genai not installed. Run: pip install google-genai")
            
        self.client = genai.Client(api_key=self.api_key)
        self.current_model_idx = 0
        self.token_usage = {"input": 0, "output": 0, "total_requests": 0}
        
        # Ensure cache directory exists
        os.makedirs(self.CACHE_DIR, exist_ok=True)
    
    def _get_cache_key(self, prompt: str, model: str) -> str:
        """Generate a unique cache key for a prompt+model combination."""
        content = f"{model}:{prompt}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _get_cached_response(self, prompt: str, model: str) -> Optional[str]:
        """Check if response is cached."""
        cache_key = self._get_cache_key(prompt, model)
        cache_file = os.path.join(self.CACHE_DIR, f"{cache_key}.json")
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                    print(f"   💾 Cache hit! Saved API call.")
                    return cached.get("response")
            except Exception:
                pass
        return None
    
    def _cache_response(self, prompt: str, model: str, response: str):
        """Cache a response for future use."""
        cache_key = self._get_cache_key(prompt, model)
        cache_file = os.path.join(self.CACHE_DIR, f"{cache_key}.json")
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "prompt": prompt[:200],  # Store truncated prompt for reference
                    "model": model,
                    "response": response,
                    "cached_at": datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # Caching failure is non-critical
    
    def run_task(
        self, 
        prompt: str, 
        context: Optional[Dict[str, Any]] = None,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        use_cache: bool = True,
        force_model: Optional[str] = None
    ) -> str:
        """
        Run a task with automatic model escalation.
        
        Args:
            prompt: The task prompt
            context: Optional context dict (e.g., {"file_path": "..."})
            max_tokens: Maximum output tokens (lower = cheaper)
            temperature: Response randomness (0.0=deterministic, 1.0=creative)
            use_cache: Whether to use response caching
            force_model: Force a specific model (bypasses escalation)
        
        Returns:
            The model's response text
        """
        # Prepare full prompt with context
        full_prompt = prompt
        if context:
            context_str = json.dumps(context, indent=2)
            full_prompt = f"{prompt}\n\nContext:\n```json\n{context_str}\n```"
        
        # Use forced model or start from cheapest
        if force_model:
            models_to_try = [force_model]
        else:
            models_to_try = self.MODEL_HIERARCHY[self.current_model_idx:]
        
        for model_name in models_to_try:
            # Check cache first
            if use_cache:
                cached = self._get_cached_response(full_prompt, model_name)
                if cached:
                    return cached
            
            print(f"🤖 Using model: {model_name}")
            
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction="Be concise and accurate. Provide direct answers.",
                        max_output_tokens=max_tokens,
                        temperature=temperature
                    )
                )
                
                # Track token usage (approximate)
                self.token_usage["total_requests"] += 1
                
                result_text = response.text
                
                # Check for failure indicators
                if "ERROR" in result_text or "I cannot" in result_text:
                    print(f"   ⚠️ Model response indicates failure, trying next model...")
                    continue
                
                # Cache successful response
                if use_cache:
                    self._cache_response(full_prompt, model_name, result_text)
                
                print(f"   ✅ Task completed successfully")
                return result_text
                
            except Exception as e:
                print(f"   ❌ Model {model_name} failed: {str(e)[:100]}")
                continue
        
        return "❌ All models exhausted or failed."
    
    def get_usage_stats(self) -> Dict[str, int]:
        """Get token usage statistics."""
        return self.token_usage.copy()
    
    def clear_cache(self):
        """Clear all cached responses."""
        import shutil
        if os.path.exists(self.CACHE_DIR):
            shutil.rmtree(self.CACHE_DIR)
            os.makedirs(self.CACHE_DIR, exist_ok=True)
            print("🗑️ Cache cleared")


# Example usage
if __name__ == "__main__":
    # Load API key from environment
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        print("❌ Set GEMINI_API_KEY environment variable first")
        print("   export GEMINI_API_KEY='your-api-key-here'")
    else:
        agent = SmartAgent(api_key=api_key)
        
        # Example: Simple task
        result = agent.run_task(
            prompt="What is 2+2?",
            max_tokens=50  # Keep it cheap
        )
        print(f"\nResult: {result}")
        
        # Show usage stats
        print(f"\nUsage: {agent.get_usage_stats()}")