#!/usr/bin/env python3
"""
Simple LLM Demo: Quick demonstration of OpenRouter integration
"""

import asyncio
from src.agents.registry import register_default_agents
from src.agents.supervisor import AgentSupervisor
from src.llm.openrouter_client import OpenRouterClient
import structlog
import json

logger = structlog.get_logger()


async def create_llm_agent(supervisor, agent_type, name, config):
    """Helper to create LLM agents"""
    from src.agents.llm_agent import (
        LLMWorkerAgent, LLMAnalyzerAgent, 
        LLMValidatorAgent, LLMOrchestratorAgent
    )
    import uuid
    
    agent_classes = {
        "llm_worker": LLMWorkerAgent,
        "llm_analyzer": LLMAnalyzerAgent,
        "llm_validator": LLMValidatorAgent,
        "llm_orchestrator": LLMOrchestratorAgent
    }
    
    agent_id = str(uuid.uuid4())
    agent_class = agent_classes[agent_type]
    
    llm_client = config.pop('llm_client', None)
    model = config.pop('model', 'openai/gpt-4o-mini')
    temperature = config.pop('temperature', 0.7)
    
    agent = agent_class(agent_id, name, llm_client, model, temperature)
    await agent.initialize()
    
    supervisor._agents[agent_id] = agent
    return agent


async def demo_customer_analysis():
    """Demo: Analyze customer feedback with multiple LLMs"""
    print("\n🤖 Customer Feedback Analysis Demo\n")
    
    try:
        register_default_agents()
    except ValueError:
        pass
    
    supervisor = AgentSupervisor()
    
    async with OpenRouterClient() as llm_client:
        # Create specialized agents
        print("Creating AI agents...")
        
        sentiment_analyzer = await create_llm_agent(
            supervisor,
            "llm_analyzer",
            "sentiment_analyzer",
            {
                "llm_client": llm_client,
                "model": "openai/gpt-4o-mini",
                "temperature": 0.3
            }
        )
        
        insight_generator = await create_llm_agent(
            supervisor,
            "llm_analyzer",
            "insight_generator",
            {
                "llm_client": llm_client,
                "model": "anthropic/claude-3.7-sonnet",
                "temperature": 0.5
            }
        )
        
        # Sample feedback
        feedback_data = {
            "feedback": [
                "The new UI is amazing! So much easier to navigate.",
                "Shipping took forever. Very disappointed.",
                "Customer support was helpful but response time was slow.",
                "Love the product quality, worth every penny!",
                "The mobile app crashes frequently on Android."
            ]
        }
        
        # Analyze sentiment
        print("\n📊 Analyzing sentiment...")
        sentiment_result = await sentiment_analyzer.process_task({
            "description": "Analyze the sentiment of each feedback item",
            "data": feedback_data
        })
        
        print("\nSentiment Analysis:")
        print(json.dumps(sentiment_result.get("result", {}), indent=2))
        
        # Generate insights
        print("\n💡 Generating insights...")
        insights = await insight_generator.process_task({
            "description": "Generate actionable business insights from this feedback",
            "data": {
                "feedback": feedback_data["feedback"],
                "sentiment_analysis": sentiment_result.get("result", {})
            }
        })
        
        print("\nBusiness Insights:")
        print(json.dumps(insights.get("result", {}), indent=2))
        
        # Token usage summary
        print("\n📈 Token Usage Summary:")
        print(f"Sentiment Analysis: {sentiment_result.get('metadata', {}).get('usage', {}).get('total_tokens', 0)} tokens")
        print(f"Insight Generation: {insights.get('metadata', {}).get('usage', {}).get('total_tokens', 0)} tokens")


async def demo_code_explanation():
    """Demo: Explain code using different models"""
    print("\n📝 Code Explanation Demo\n")
    
    try:
        register_default_agents()
    except ValueError:
        pass
    
    supervisor = AgentSupervisor()
    
    async with OpenRouterClient() as llm_client:
        # Code to explain
        code_sample = '''
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
'''
        
        # Use different models for different perspectives
        models = [
            ("openai/gpt-4o-mini", "GPT-4", 0.3),
            ("google/gemini-2.5-flash", "Gemini", 0.3),
            ("mistralai/mistral-small-3.2-24b-instruct:free", "Mistral", 0.3)
        ]
        
        print(f"Code to explain:\n```python{code_sample}```\n")
        
        for model_id, model_name, temp in models:
            print(f"\n{model_name} Explanation:")
            
            agent = await create_llm_agent(
                supervisor,
                "llm_worker",
                f"explainer_{model_name}",
                {
                    "llm_client": llm_client,
                    "model": model_id,
                    "temperature": temp
                }
            )
            
            result = await agent.process_task({
                "description": "Explain this code in simple terms for a beginner",
                "data": {"code": code_sample}
            })
            
            print(result.get("result", "No explanation provided"))
            print(f"Tokens used: {result.get('metadata', {}).get('usage', {}).get('total_tokens', 0)}")


async def main():
    """Run demos"""
    try:
        await demo_customer_analysis()
        print("\n" + "="*60 + "\n")
        await demo_code_explanation()
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())