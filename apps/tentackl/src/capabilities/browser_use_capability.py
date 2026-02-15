"""
Browser-Use Capability for Tentackl

This module provides web browsing capabilities using the browser-use library,
allowing agents to interact with web pages through AI-driven automation.
"""

import asyncio
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
import structlog
from browser_use import Agent as BrowserAgent
from browser_use.llm import ChatOpenAI, ChatAnthropic, ChatOpenRouter, BaseChatModel
from browser_use.browser import BrowserConfig

from ..interfaces.configurable_agent import AgentCapability
from .capability_registry import ToolDefinition

logger = structlog.get_logger(__name__)


class BrowserUseWrapper:
    """Wrapper for browser-use Agent to fit Tentackl's capability system"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.browser_agent: Optional[BrowserAgent] = None
        self._initialized = False
        
        # Configuration
        self.llm_provider = config.get("llm_provider", "openai")
        self.llm_model = config.get("llm_model", "gpt-4o-mini")
        self.llm_temperature = config.get("llm_temperature", 0.3)
        self.headless = config.get("headless", True)
        self.max_steps = config.get("max_steps", 20)
        self.save_screenshots = config.get("save_screenshots", True)
        self.screenshot_path = config.get("screenshot_path", "/tmp/browser_screenshots")
        
    def _create_llm(self) -> BaseChatModel:
        """Create the appropriate LLM instance based on configuration"""
        if self.llm_provider == "openai":
            return ChatOpenAI(
                model=self.llm_model,
                temperature=self.llm_temperature
            )
        elif self.llm_provider == "anthropic":
            return ChatAnthropic(
                model=self.llm_model,
                temperature=self.llm_temperature
            )
        elif self.llm_provider == "openrouter":
            import os
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY environment variable not set")
            return ChatOpenRouter(
                model=self.llm_model,
                temperature=self.llm_temperature,
                api_key=api_key
            )
        else:
            raise ValueError(f"Unknown LLM provider: {self.llm_provider}")
    
    async def initialize(self, task: str) -> None:
        """Initialize the browser agent with a specific task"""
        if self._initialized and self.browser_agent:
            # If already initialized, update the task
            self.browser_agent.task = task
            return
            
        try:
            # Create browser config
            browser_config = BrowserConfig(
                headless=self.headless,
                screenshot_dir=self.screenshot_path if self.save_screenshots else None
            )
            
            # Create LLM
            llm = self._create_llm()
            
            # Create browser agent
            self.browser_agent = BrowserAgent(
                task=task,
                llm=llm,
                browser_config=browser_config,
                max_steps=self.max_steps
            )
            
            self._initialized = True
            logger.info(
                "Browser-use agent initialized",
                provider=self.llm_provider,
                model=self.llm_model,
                headless=self.headless
            )
            
        except Exception as e:
            logger.error("Failed to initialize browser-use agent", error=str(e))
            raise
    
    async def execute_task(self, task: str, additional_instructions: Optional[List[str]] = None) -> Dict[str, Any]:
        """Execute a browser task"""
        try:
            # Prepare the full task description
            full_task = task
            if additional_instructions:
                full_task += "\n\nAdditional instructions:\n" + "\n".join(f"- {inst}" for inst in additional_instructions)
            
            # Initialize or update with new task
            await self.initialize(full_task)
            
            # Run the browser agent
            logger.info("Executing browser task", task=task[:100])
            result = await self.browser_agent.run()
            
            # Extract the final result text if available
            final_result_text = None
            if hasattr(result, 'all_results') and result.all_results:
                # Find the done action result
                for action_result in result.all_results:
                    if action_result.is_done and action_result.extracted_content:
                        final_result_text = action_result.extracted_content
                        break
            
            # Extract relevant information from the result
            return {
                "success": True,
                "result_text": final_result_text or str(result),
                "task": task,
                "screenshots": self._get_screenshots() if self.save_screenshots else [],
                "steps_taken": self.browser_agent.n_steps if hasattr(self.browser_agent, 'n_steps') else None,
                "raw_result": result  # Keep raw result for debugging
            }
            
        except Exception as e:
            logger.error("Browser task execution failed", task=task, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "task": task
            }
    
    async def browse_and_extract(self, url: str, extraction_goal: str) -> Dict[str, Any]:
        """Browse to a URL and extract specific information"""
        task = f"Navigate to {url} and {extraction_goal}"
        return await self.execute_task(task)
    
    async def fill_form(self, url: str, form_data: Dict[str, Any], submit: bool = False) -> Dict[str, Any]:
        """Fill a form on a webpage"""
        task = f"Navigate to {url} and fill the form with the following data:\n"
        for field, value in form_data.items():
            task += f"- {field}: {value}\n"
        
        if submit:
            task += "\nSubmit the form after filling it."
        else:
            task += "\nDo not submit the form, just fill it."
            
        return await self.execute_task(task)
    
    async def monitor_page(self, url: str, conditions: List[str]) -> Dict[str, Any]:
        """Monitor a page for specific conditions"""
        task = f"Navigate to {url} and check for the following conditions:\n"
        task += "\n".join(f"- {condition}" for condition in conditions)
        task += "\nReport on each condition whether it is met or not."
        
        return await self.execute_task(task)
    
    async def search_and_analyze(self, search_query: str, analysis_requirements: List[str]) -> Dict[str, Any]:
        """Perform a web search and analyze results"""
        task = f"Search for '{search_query}' on the web and analyze the results based on:\n"
        task += "\n".join(f"- {req}" for req in analysis_requirements)
        
        return await self.execute_task(task)
    
    async def multi_step_workflow(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute a multi-step browser workflow"""
        task = "Complete the following workflow:\n"
        for i, step in enumerate(steps, 1):
            task += f"\nStep {i}: {step.get('description', 'No description')}"
            if 'url' in step:
                task += f"\n  - URL: {step['url']}"
            if 'actions' in step:
                task += f"\n  - Actions: {', '.join(step['actions'])}"
            if 'expected_result' in step:
                task += f"\n  - Expected result: {step['expected_result']}"
        
        return await self.execute_task(task)
    
    def _get_screenshots(self) -> List[str]:
        """Get list of screenshots taken during execution"""
        # This would need to be implemented based on how browser-use stores screenshots
        import os
        if os.path.exists(self.screenshot_path):
            return [f for f in os.listdir(self.screenshot_path) if f.endswith('.png')]
        return []
    
    async def cleanup(self):
        """Cleanup browser resources"""
        # browser-use handles its own cleanup
        self._initialized = False
        logger.info("Browser-use agent cleaned up")


async def browser_use_handler(config: Dict[str, Any]) -> BrowserUseWrapper:
    """Factory function for creating browser-use wrapper instances"""
    wrapper = BrowserUseWrapper(config)
    return wrapper


# Define the browser methods that will be exposed
class BrowserUseMethods:
    """Methods that will be injected into agents with browser capability"""
    
    def __init__(self, wrapper: BrowserUseWrapper):
        self._wrapper = wrapper
    
    async def browse(self, task: str) -> Dict[str, Any]:
        """Execute a browser task using natural language instructions"""
        return await self._wrapper.execute_task(task)
    
    async def browse_url(self, url: str, goal: str) -> Dict[str, Any]:
        """Browse to a URL with a specific goal"""
        return await self._wrapper.browse_and_extract(url, goal)
    
    async def fill_web_form(self, url: str, data: Dict[str, Any], submit: bool = False) -> Dict[str, Any]:
        """Fill a form on a webpage"""
        return await self._wrapper.fill_form(url, data, submit)
    
    async def monitor_web_page(self, url: str, conditions: List[str]) -> Dict[str, Any]:
        """Monitor a webpage for conditions"""
        return await self._wrapper.monitor_page(url, conditions)
    
    async def web_search(self, query: str, analyze: List[str]) -> Dict[str, Any]:
        """Search the web and analyze results"""
        return await self._wrapper.search_and_analyze(query, analyze)
    
    async def browser_workflow(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute a multi-step browser workflow"""
        return await self._wrapper.multi_step_workflow(steps)


# Custom handler that creates the methods object
async def browser_methods_handler(config: Dict[str, Any]) -> BrowserUseMethods:
    """Create browser methods that can be used by agents"""
    wrapper = await browser_use_handler(config)
    return BrowserUseMethods(wrapper)


# Register the capability
BROWSER_USE_CAPABILITY = ToolDefinition(
    name="browser",
    description="Browse and interact with web pages using AI-driven automation (browser-use)",
    handler=browser_methods_handler,
    config_schema={
        "type": "object",
        "properties": {
            "llm_provider": {
                "type": "string", 
                "enum": ["openai", "anthropic", "openrouter"], 
                "default": "openai",
                "description": "LLM provider to use for browser automation"
            },
            "llm_model": {
                "type": "string", 
                "default": "gpt-4o-mini",
                "description": "Specific model to use"
            },
            "llm_temperature": {
                "type": "number", 
                "default": 0.3,
                "description": "Temperature for LLM responses"
            },
            "headless": {
                "type": "boolean", 
                "default": True,
                "description": "Run browser in headless mode"
            },
            "max_steps": {
                "type": "integer", 
                "default": 20,
                "description": "Maximum steps the agent can take"
            },
            "save_screenshots": {
                "type": "boolean",
                "default": True,
                "description": "Save screenshots of browser actions"
            },
            "screenshot_path": {
                "type": "string", 
                "default": "/tmp/browser_screenshots",
                "description": "Path to save screenshots"
            }
        }
    },
    permissions_required=["network:http", "filesystem:write"],
    sandboxable=True,
    category=AgentCapability.CUSTOM
)