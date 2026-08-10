"""
Example 2: AI Gateway with Provider Routing

Demonstrates multi-provider routing with fallback and connection pooling.
"""

import asyncio

from loopy import Gateway, ModelProvider, ProviderConfig


async def main():
    # Create gateway with async context manager
    async with Gateway() as gateway:
        
        # Add multiple providers
        gateway.add_provider("openai", ProviderConfig(
            provider=ModelProvider.OPENAI,
            api_key="sk-...",  # Replace with your key
            model="gpt-4",
            rpm=60,
        ))
        
        gateway.add_provider("anthropic", ProviderConfig(
            provider=ModelProvider.ANTHROPIC,
            api_key="sk-ant-...",  # Replace with your key
            model="claude-3-opus",
            rpm=40,
        ))
        
        gateway.add_provider("ollama", ProviderConfig(
            provider=ModelProvider.OLLAMA,
            base_url="http://localhost:11434",
            model="llama3",
        ))
        
        # Route to specific provider
        try:
            response = await gateway.chat(
                "What is 2+2?",
                provider="openai",
            )
            print(f"OpenAI: {response.content}")
            print(f"Tokens: {response.tokens_used}")
            print(f"Latency: {response.latency_ms:.1f}ms")
        except Exception as e:
            print(f"OpenAI failed: {e}")
        
        # Batch requests
        messages = [
            "What is Python?",
            "What is JavaScript?",
            "What is Rust?",
        ]
        
        try:
            responses = await gateway.chat_batch(
                messages,
                provider="ollama",
                max_concurrent=3,
            )
            
            for i, resp in enumerate(responses):
                print(f"\nResponse {i+1}: {resp.content[:100]}...")
        except Exception as e:
            print(f"Batch failed: {e}")
        
        # Check logs
        logs = gateway.get_logs()
        print(f"\nTotal requests: {len(logs)}")


if __name__ == "__main__":
    asyncio.run(main())
