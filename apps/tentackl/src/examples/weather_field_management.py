#!/usr/bin/env python3
"""
Weather Field Management System Demo

This example demonstrates the complete weather-based football field management system
using Tentackl's multi-agent architecture with event-driven coordination.

Key Features:
- Event bus for webhook reception and routing
- ConfigurableAgent-based weather monitor (orchestrator)
- Field scheduler agent for booking management
- Communication coordinator for customer notifications
- Budget control and cost tracking
- State persistence for weather events
- Execution tree for workflow visualization

Prerequisites:
- OPENROUTER_API_KEY set in .env file
- Docker containers running
- Redis available

Usage:
    docker compose exec api python src/examples/weather_field_management.py
"""

import asyncio
import json
import yaml
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
import uuid
from dataclasses import dataclass, field
from enum import Enum

# Core imports
from src.agents.configurable_agent import ConfigurableAgent
from src.interfaces.agent import AgentState
from src.config.agent_config_parser import AgentConfigParser
from src.capabilities.capability_registry import CapabilityRegistry
from src.infrastructure.execution_runtime.prompt_executor import PromptExecutor
from src.llm.openrouter_client import OpenRouterClient

# Infrastructure imports
from src.budget.redis_budget_controller import RedisBudgetController
from src.interfaces.budget_controller import BudgetConfig, ResourceLimit, ResourceType
from src.infrastructure.state.redis_state_store import RedisStateStore
from src.interfaces.state_store import StateType, StateSnapshot
from src.context.redis_context_manager import RedisContextManager
from src.interfaces.context_manager import ContextIsolationLevel
from src.infrastructure.execution_runtime.redis_execution_tree import RedisExecutionTree
from src.core.execution_tree import ExecutionNode, ExecutionStatus

import structlog

logger = structlog.get_logger(__name__)


# Event Bus Components (Simplified for demo)
class EventType(Enum):
    """Types of events in the system"""
    WEATHER_UPDATE = "weather.forecast.updated"
    BOOKING_AFFECTED = "booking.affected"
    NOTIFICATION_SENT = "notification.sent"
    DECISION_MADE = "decision.made"


@dataclass
class WeatherEvent:
    """Weather event data structure"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    location: str = "Porto"
    precipitation_probability: float = 0.0
    severity: str = "low"
    affected_hours: List[int] = field(default_factory=list)
    forecast_window: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BookingInfo:
    """Booking information"""
    id: str
    field_id: str
    customer_id: str
    customer_name: str
    customer_email: str
    customer_phone: str
    start_time: datetime
    end_time: datetime
    status: str = "confirmed"


class SimpleEventBus:
    """Simplified event bus for demo purposes"""
    
    def __init__(self, state_store: RedisStateStore):
        self.state_store = state_store
        self.subscribers: Dict[EventType, List[callable]] = {}
        self._running = False
        
    async def start(self):
        """Start the event bus"""
        self._running = True
        logger.info("Event bus started")
        
    async def stop(self):
        """Stop the event bus"""
        self._running = False
        logger.info("Event bus stopped")
        
    def subscribe(self, event_type: EventType, handler: callable):
        """Subscribe to an event type"""
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(handler)
        logger.info(f"Subscribed handler to {event_type.value}")
        
    async def publish(self, event_type: EventType, data: Any):
        """Publish an event"""
        if not self._running:
            logger.warning("Event bus not running")
            return
            
        print(f"\n🚌 EVENT BUS: Publishing {event_type.value}")
        print(f"   Data: {data.get('precipitation_probability', 'N/A')}% rain probability")
        
        # Store event
        event_id = str(uuid.uuid4())
        await self.state_store.save_state(StateSnapshot(
            id=event_id,
            agent_id="event_bus",
            state_type=StateType.AGENT_STATE,
            data={
                "event_type": event_type.value,
                "data": data,
                "timestamp": datetime.utcnow().isoformat()
            }
        ))
        
        # Notify subscribers
        if event_type in self.subscribers:
            print(f"   Found {len(self.subscribers[event_type])} subscribers")
            for handler in self.subscribers[event_type]:
                try:
                    await handler(data)
                except Exception as e:
                    logger.error(f"Error in event handler: {e}")


class WeatherFieldManagementSystem:
    """Main system orchestrating weather-based field management"""
    
    def __init__(self):
        # Infrastructure components
        self.state_store = RedisStateStore(
            redis_url="redis://redis:6379",
            db=7,
            key_prefix="weather_demo"
        )
        
        self.budget_controller = RedisBudgetController(
            redis_url="redis://redis:6379",
            db=7,
            key_prefix="weather_budget"
        )
        
        self.context_manager = RedisContextManager(
            redis_url="redis://redis:6379",
            db=7,
            key_prefix="weather_context"
        )
        
        self.execution_tree = RedisExecutionTree(
            redis_url="redis://redis:6379",
            db=7,
            key_prefix="weather_tree"
        )
        
        self.event_bus = SimpleEventBus(self.state_store)
        
        # Agent components
        self.capability_registry = CapabilityRegistry()
        self.llm_client = OpenRouterClient()
        self.prompt_executor = PromptExecutor(self.llm_client)
        
        # System state
        self.agents: Dict[str, ConfigurableAgent] = {}
        self.bookings: List[BookingInfo] = []
        self.tree_id: Optional[str] = None
        
    async def initialize(self):
        """Initialize the system"""
        logger.info("Initializing Weather Field Management System")
        
        # Initialize OpenRouter client
        await self.llm_client.__aenter__()
        
        # Start event bus
        await self.event_bus.start()
        
        # Create execution tree
        self.tree_id = await self.execution_tree.create_tree(
            "weather_field_management",
            "weather_system",  # root_agent_id
            metadata={"start_time": datetime.utcnow().isoformat()}
        )
        
        # Initialize mock bookings
        self._initialize_mock_bookings()
        
        # Set up event handlers
        self.event_bus.subscribe(
            EventType.WEATHER_UPDATE,
            self.handle_weather_update
        )
        
        # Create and configure agents
        await self._create_agents()
        
        logger.info("System initialized successfully")
        
    def _initialize_mock_bookings(self):
        """Create mock bookings for demo"""
        base_time = datetime.utcnow().replace(hour=14, minute=0, second=0, microsecond=0)
        
        self.bookings = [
            BookingInfo(
                id="booking_001",
                field_id="field_a",
                customer_id="cust_001",
                customer_name="João Silva",
                customer_email="joao@example.com",
                customer_phone="+351912345678",
                start_time=base_time,
                end_time=base_time + timedelta(hours=1)
            ),
            BookingInfo(
                id="booking_002",
                field_id="field_b",
                customer_id="cust_002",
                customer_name="Maria Santos",
                customer_email="maria@example.com",
                customer_phone="+351923456789",
                start_time=base_time + timedelta(hours=1, minutes=30),
                end_time=base_time + timedelta(hours=2, minutes=30)
            ),
            BookingInfo(
                id="booking_003",
                field_id="field_a",
                customer_id="cust_003",
                customer_name="Pedro Costa",
                customer_email="pedro@example.com",
                customer_phone="+351934567890",
                start_time=base_time + timedelta(hours=3),
                end_time=base_time + timedelta(hours=4)
            )
        ]
        
    async def _create_agents(self):
        """Create all agents with configurations"""
        # Create weather monitor configuration
        weather_monitor_config = {
            "name": "weather_monitor_porto",
            "type": "orchestrator",
            "version": "1.0.0",
            "description": "Weather monitoring agent for Porto football fields",
            "capabilities": [
                {
                    "tool": "weather_analysis",
                    "config": {"thresholds": {"low": 0.3, "medium": 0.6, "high": 0.8}}
                },
                {
                    "tool": "decision_making",
                    "config": {"strategies": ["proactive", "reactive"]}
                }
            ],
            "prompt_template": """You are a weather monitoring agent for Porto football fields.
Analyze the weather data and determine the appropriate response.

Weather Data:
- Location: {location}
- Precipitation Probability: {precipitation_probability}%
- Severity: {severity}
- Affected Hours: {affected_hours}
- Current Time: {current_time}

Current Bookings:
{current_bookings}

Decision Thresholds:
- 0-29%: No action required
- 30-59%: Monitor status, flag at-risk bookings
- 60-79%: Alert status, proactive notifications
- 80-100%: Action required, automatic rescheduling

Based on the precipitation probability and affected hours, determine:
1. The action level (none/monitor/alert/action)
2. Which bookings are affected
3. What actions to take
4. Priority of actions

You MUST provide your analysis as a valid JSON object with these fields:
- action_level: string
- affected_booking_ids: list of strings  
- recommended_actions: list of action objects
- priority: string (low/medium/high/critical)
- reasoning: string
- confidence: float (0-1)

Respond with JSON only, no markdown formatting or extra text.""",
            "execution_strategy": "sequential",
            "state_schema": {
                "required": ["location", "precipitation_probability", "affected_hours"],
                "output": ["action_level", "affected_booking_ids", "recommended_actions", "priority"],
                "checkpoint": {"enabled": True, "interval": 1}
            },
            "resources": {
                "model": "gpt-4o-mini",
                "max_tokens": 1000,
                "timeout": 30,
                "temperature": 0.3,
                "response_format": {"type": "json_object"}
            },
            "success_metrics": [
                {
                    "metric": "confidence",
                    "threshold": 0.7,
                    "operator": "gte"
                }
            ]
        }
        
        # Create field scheduler configuration
        field_scheduler_config = {
            "name": "field_scheduler_porto",
            "type": "data_processor",
            "version": "1.0.0",
            "description": "Field scheduling agent for rescheduling affected bookings",
            "capabilities": [
                {
                    "tool": "booking_queries",
                    "config": {"database": "bookings_db"}
                },
                {
                    "tool": "schedule_optimization",
                    "config": {"algorithm": "greedy_best_fit"}
                }
            ],
            "prompt_template": """You are a field scheduling agent. Find alternative slots for weather-affected bookings.

Affected Bookings:
{affected_bookings}

Available Slots:
{available_slots}

Customer Preferences:
- Minimize disruption
- Keep similar time if possible
- Same field preferred
- Group bookings together when possible

Generate rescheduling proposals that optimize for customer convenience.
For each affected booking, provide:
1. Original slot
2. Proposed new slot(s)
3. Reasoning for the proposal

Return JSON with:
- proposals: list of proposal objects
- optimization_score: float (0-1)
- conflicts_resolved: boolean""",
            "execution_strategy": "sequential",
            "state_schema": {
                "required": ["affected_bookings", "available_slots"],
                "output": ["proposals", "optimization_score", "conflicts_resolved"],
                "checkpoint": {"enabled": True}
            },
            "resources": {
                "model": "gpt-3.5-turbo",
                "max_tokens": 1500,
                "timeout": 45,
                "temperature": 0.1
            },
            "success_metrics": [
                {
                    "metric": "optimization_score",
                    "threshold": 0.7,
                    "operator": "gte"
                }
            ]
        }
        
        # Create communication coordinator configuration
        communication_coordinator_config = {
            "name": "communication_porto",
            "type": "notifier",
            "version": "1.0.0",
            "description": "Communication agent for customer notifications",
            "capabilities": [
                {
                    "tool": "message_generation",
                    "config": {"templates": ["sms", "email", "push"]}
                },
                {
                    "tool": "channel_selection",
                    "config": {"priorities": ["sms", "email", "app"]}
                }
            ],
            "prompt_template": """You are a communication coordinator for Porto football fields.
Generate personalized messages for weather-affected bookings.

Customer Information:
{customer_info}

Booking Details:
{booking_details}

Weather Situation:
{weather_info}

Rescheduling Options:
{rescheduling_options}

Message Type: {message_type}
Channel: {channel}

Generate a friendly, helpful, and proactive message that:
1. Explains the weather situation
2. Shows empathy for the inconvenience
3. Offers clear rescheduling options
4. Provides easy action steps

Keep messages concise for SMS (160 chars), detailed for email.
Return JSON with:
- message: string
- subject: string (for email)
- call_to_action: string
- urgency: string (low/medium/high)""",
            "execution_strategy": "parallel",
            "state_schema": {
                "required": ["customer_info", "booking_details", "weather_info", "message_type"],
                "output": ["message", "subject", "call_to_action", "urgency"],
                "checkpoint": {"enabled": True}
            },
            "resources": {
                "model": "gpt-3.5-turbo",
                "max_tokens": 500,
                "timeout": 20,
                "temperature": 0.7
            },
            "success_metrics": [
                {
                    "metric": "message_quality",
                    "threshold": 0.8,
                    "operator": "gte"
                }
            ]
        }
        
        # Create budgets for agents
        for agent_id, budget_limit in [
            ("weather_monitor", 5.00),
            ("field_scheduler", 3.00),
            ("communication_coordinator", 2.00)
        ]:
            budget_config = BudgetConfig(
                limits=[
                    ResourceLimit(
                        resource_type=ResourceType.LLM_COST,
                        limit=budget_limit,
                        hard_limit=True
                    ),
                    ResourceLimit(
                        resource_type=ResourceType.LLM_CALLS,
                        limit=100,
                        hard_limit=False
                    )
                ],
                owner="weather_system",
                created_at=datetime.utcnow(),
                metadata={"agent_type": agent_id}
            )
            await self.budget_controller.create_budget(agent_id, budget_config)
        
        # Parse and create agents
        parser = AgentConfigParser()
        
        # Weather Monitor
        config = await parser.parse(weather_monitor_config)
        self.agents["weather_monitor"] = ConfigurableAgent(
            agent_id="weather_monitor",
            config=config,
            budget_controller=self.budget_controller,
            state_store=self.state_store,
            context_manager=self.context_manager,
            capability_binder=self.capability_registry,
            prompt_executor=self.prompt_executor
        )
        
        # Field Scheduler
        config = await parser.parse(field_scheduler_config)
        self.agents["field_scheduler"] = ConfigurableAgent(
            agent_id="field_scheduler",
            config=config,
            budget_controller=self.budget_controller,
            state_store=self.state_store,
            context_manager=self.context_manager,
            capability_binder=self.capability_registry,
            prompt_executor=self.prompt_executor
        )
        
        # Communication Coordinator
        config = await parser.parse(communication_coordinator_config)
        self.agents["communication_coordinator"] = ConfigurableAgent(
            agent_id="communication_coordinator",
            config=config,
            budget_controller=self.budget_controller,
            state_store=self.state_store,
            context_manager=self.context_manager,
            capability_binder=self.capability_registry,
            prompt_executor=self.prompt_executor
        )
        
        # Wait for initialization
        await asyncio.sleep(0.5)
        
    async def handle_weather_update(self, weather_event: Dict[str, Any]):
        """Handle incoming weather update event"""
        print(f"\n🌦️  WEATHER MONITOR: Received weather event")
        print(f"   Precipitation: {weather_event['precipitation_probability']}%")
        print(f"   Severity: {weather_event['severity']}")
        print(f"   Affected hours: {weather_event['affected_hours']}")
        
        # Create weather monitor node
        monitor_node = ExecutionNode(
            name="weather_monitor",
            agent_id="weather_monitor",
            task_data=weather_event,
            metadata={"event_type": "weather_update"}
        )
        await self.execution_tree.add_node(self.tree_id, monitor_node)
        await self.execution_tree.update_node_status(
            self.tree_id,
            monitor_node.id,
            ExecutionStatus.RUNNING
        )
        
        print("\n🤖 AGENT: Weather Monitor analyzing...")
        
        # Add booking information to the weather event
        weather_event_with_bookings = weather_event.copy()
        weather_event_with_bookings["current_bookings"] = [
            {
                "id": b.id,
                "field_id": b.field_id,
                "customer_name": b.customer_name,
                "start_time": b.start_time.hour,
                "end_time": b.end_time.hour
            }
            for b in self.bookings
        ]
        
        # Execute weather monitor
        result = await self.agents["weather_monitor"].execute(weather_event_with_bookings)
        
        await self.execution_tree.update_node_status(
            self.tree_id,
            monitor_node.id,
            ExecutionStatus.COMPLETED if result.state == AgentState.COMPLETED else ExecutionStatus.FAILED,
            result.result
        )
        
        if result.state == AgentState.COMPLETED and result.result:
            # Handle both dict and wrapped dict cases
            data = result.result
            if isinstance(data, dict) and "result" in data and isinstance(data["result"], str):
                # Try to parse the wrapped JSON string
                try:
                    data = json.loads(data["result"])
                except:
                    pass
            
            # Now check if we have the expected fields
            if isinstance(data, dict) and "action_level" in data:
                action_level = data.get("action_level", "none")
                affected_booking_ids = data.get("affected_booking_ids", [])
                
                print(f"\n✅ DECISION SUCCESSFUL")
                print(f"📊 Action level: {action_level}")
                print(f"   Affected bookings: {affected_booking_ids}")
                print(f"   Confidence: {data.get('confidence', 'N/A')}")
                print(f"   Reasoning: {data.get('reasoning', 'N/A')}")
                
                # If action needed, spawn child agents
                if action_level in ["alert", "action"] and affected_booking_ids:
                    print(f"\n🚀 SPAWNING CHILD AGENTS for {len(affected_booking_ids)} bookings")
                    await self._handle_affected_bookings(
                        affected_booking_ids,
                        weather_event,
                        data,
                        monitor_node.id
                    )
            else:
                print(f"\n❌ Could not parse decision from response")
                print(f"   Response type: {type(data)}")
                if isinstance(data, dict):
                    print(f"   Response keys: {list(data.keys())}")
        else:
            print(f"\n❌ DECISION FAILED: {result.state}")
            print(f"   Error: {result.error}")
            if result.result:
                print(f"   Response: {json.dumps(result.result, indent=2)}")
                
    async def _handle_affected_bookings(
        self,
        affected_booking_ids: List[str],
        weather_event: Dict[str, Any],
        monitor_result: Dict[str, Any],
        parent_node_id: str
    ):
        """Handle bookings affected by weather"""
        # Get affected bookings
        affected_bookings = [
            b for b in self.bookings
            if b.id in affected_booking_ids
        ]
        
        # Create field scheduler node
        scheduler_node = ExecutionNode(
            name="field_scheduler",
            agent_id="field_scheduler",
            dependencies={parent_node_id},
            task_data={
                "affected_bookings": [
                    {
                        "id": b.id,
                        "field_id": b.field_id,
                        "start_time": b.start_time.isoformat(),
                        "end_time": b.end_time.isoformat(),
                        "customer_name": b.customer_name
                    }
                    for b in affected_bookings
                ],
                "available_slots": self._generate_available_slots()
            }
        )
        await self.execution_tree.add_node(self.tree_id, scheduler_node)
        
        # Execute field scheduler
        await self.execution_tree.update_node_status(
            self.tree_id,
            scheduler_node.id,
            ExecutionStatus.RUNNING
        )
        
        print("\n📅 FIELD SCHEDULER: Finding alternative slots...")
        
        scheduler_result = await self.agents["field_scheduler"].execute({
            "affected_bookings": scheduler_node.task_data["affected_bookings"],
            "available_slots": scheduler_node.task_data["available_slots"]
        })
        
        await self.execution_tree.update_node_status(
            self.tree_id,
            scheduler_node.id,
            ExecutionStatus.COMPLETED if scheduler_result.state == AgentState.COMPLETED else ExecutionStatus.FAILED,
            scheduler_result.result
        )
        
        # If rescheduling successful, send notifications
        if scheduler_result.state == AgentState.COMPLETED and scheduler_result.result:
            print(f"\n✅ RESCHEDULING COMPLETE")
            print(f"   Optimization score: {scheduler_result.result.get('optimization_score', 'N/A')}")
            
            proposals = scheduler_result.result.get("proposals", [])
            
            # Create communication tasks
            comm_tasks = []
            for i, booking in enumerate(affected_bookings):
                proposal = proposals[i] if i < len(proposals) else None
                
                comm_node = ExecutionNode(
                    name=f"notify_customer_{booking.customer_id}",
                    agent_id="communication_coordinator",
                    dependencies={scheduler_node.id},
                    task_data={
                        "customer_info": {
                            "name": booking.customer_name,
                            "email": booking.customer_email,
                            "phone": booking.customer_phone
                        },
                        "booking_details": {
                            "id": booking.id,
                            "original_time": booking.start_time.isoformat(),
                            "field": booking.field_id
                        },
                        "weather_info": {
                            "probability": weather_event["precipitation_probability"],
                            "time": weather_event["affected_hours"]
                        },
                        "rescheduling_options": proposal,
                        "message_type": "weather_alert",
                        "channel": "sms"
                    }
                )
                await self.execution_tree.add_node(self.tree_id, comm_node)
                
                comm_tasks.append(self._send_notification(comm_node))
            
            # Execute all notifications in parallel
            print(f"\n📧 SENDING NOTIFICATIONS to {len(comm_tasks)} customers...")
            await asyncio.gather(*comm_tasks)
            
    async def _send_notification(self, comm_node: ExecutionNode):
        """Send a single notification"""
        await self.execution_tree.update_node_status(
            self.tree_id,
            comm_node.id,
            ExecutionStatus.RUNNING
        )
        
        result = await self.agents["communication_coordinator"].execute(comm_node.task_data)
        
        await self.execution_tree.update_node_status(
            self.tree_id,
            comm_node.id,
            ExecutionStatus.COMPLETED if result.state == AgentState.COMPLETED else ExecutionStatus.FAILED,
            result.result
        )
        
        if result.state == AgentState.COMPLETED and result.result:
            print(f"   ✉️  Sent to {comm_node.task_data['customer_info']['name']} via {comm_node.task_data['channel']}")
            
            # Publish notification event
            await self.event_bus.publish(
                EventType.NOTIFICATION_SENT,
                {
                    "customer_id": comm_node.task_data["customer_info"]["name"],
                    "channel": comm_node.task_data["channel"],
                    "message": result.result.get("message", ""),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            
    def _generate_available_slots(self) -> List[Dict[str, Any]]:
        """Generate mock available slots for rescheduling"""
        base_time = datetime.utcnow().replace(hour=18, minute=0, second=0, microsecond=0)
        slots = []
        
        for i in range(5):
            for field in ["field_a", "field_b"]:
                start = base_time + timedelta(hours=i)
                slots.append({
                    "field_id": field,
                    "start_time": start.isoformat(),
                    "end_time": (start + timedelta(hours=1)).isoformat(),
                    "available": True
                })
                
        return slots
        
    async def simulate_weather_webhook(self, precipitation_probability: float):
        """Simulate an incoming weather webhook"""
        weather_event = {
            "id": str(uuid.uuid4()),
            "source": "weather_api",
            "location": "Porto",
            "precipitation_probability": precipitation_probability,
            "severity": "high" if precipitation_probability > 70 else "medium" if precipitation_probability > 40 else "low",
            "affected_hours": [14, 15, 16, 17] if precipitation_probability > 60 else [15, 16],
            "forecast_window": {
                "start": datetime.utcnow().isoformat(),
                "end": (datetime.utcnow() + timedelta(hours=6)).isoformat()
            },
            "current_time": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Simulating weather webhook: {precipitation_probability}% rain probability")
        
        # Publish to event bus
        await self.event_bus.publish(EventType.WEATHER_UPDATE, weather_event)
        
    async def show_system_status(self):
        """Display current system status"""
        print("\n" + "="*60)
        print("WEATHER FIELD MANAGEMENT SYSTEM STATUS")
        print("="*60)
        
        # Budget status
        print("\n--- Budget Usage ---")
        for agent_id in ["weather_monitor", "field_scheduler", "communication_coordinator"]:
            usage = await self.budget_controller.get_usage(agent_id)
            if usage:
                cost_usage = next((u for u in usage if u.resource_type == ResourceType.LLM_COST), None)
                if cost_usage:
                    print(f"{agent_id}: ${cost_usage.current:.4f} / ${cost_usage.limit:.2f}")
                    
        # Execution tree status
        print("\n--- Execution Tree ---")
        tree_snapshot = await self.execution_tree.get_tree_snapshot(self.tree_id)
        if tree_snapshot:
            print(f"Total nodes: {len(tree_snapshot.nodes)}")
            
            status_counts = {}
            for node in tree_snapshot.nodes.values():
                status_counts[node.status] = status_counts.get(node.status, 0) + 1
                
            for status, count in status_counts.items():
                print(f"  {status.value}: {count}")
                
        # Recent events
        print("\n--- Recent Events ---")
        events = await self.state_store.get_state_history("event_bus", limit=5)
        for event in events:
            event_data = event.data
            print(f"  {event_data.get('event_type', 'unknown')}: {event_data.get('timestamp', 'N/A')}")
            
        print("\n" + "="*60)


async def run_demo():
    """Run the weather field management demo"""
    print("\n" + "="*70)
    print("WEATHER FIELD MANAGEMENT SYSTEM DEMO")
    print("="*70)
    print("\nThis demo simulates a weather-based football field management system")
    print("that automatically handles weather events and coordinates responses.\n")
    
    # Initialize system
    system = WeatherFieldManagementSystem()
    await system.initialize()
    
    print("\nSystem initialized with:")
    print(f"- {len(system.bookings)} active bookings")
    print(f"- {len(system.agents)} configured agents")
    print("- Event bus running")
    print("- Execution tree created")
    
    # Demo scenarios
    scenarios = [
        ("Low rain probability (25%)", 25),
        ("Medium rain probability (45%)", 45),
        ("High rain probability (75%)", 75),
        ("Critical rain probability (90%)", 90)
    ]
    
    print("\nAvailable scenarios:")
    for i, (desc, _) in enumerate(scenarios, 1):
        print(f"{i}. {desc}")
    print("5. Custom probability")
    print("6. Show system status")
    print("0. Exit")
    
    while True:
        try:
            choice = input("\nSelect scenario (0-6): ")
            choice = int(choice)
            
            if choice == 0:
                break
            elif 1 <= choice <= 4:
                desc, probability = scenarios[choice - 1]
                print(f"\n--- Running: {desc} ---")
                await system.simulate_weather_webhook(probability)
                await asyncio.sleep(3)  # Wait for processing
                await system.show_system_status()
            elif choice == 5:
                probability = float(input("Enter rain probability (0-100): "))
                print(f"\n--- Running: Custom {probability}% ---")
                await system.simulate_weather_webhook(probability)
                await asyncio.sleep(3)
                await system.show_system_status()
            elif choice == 6:
                await system.show_system_status()
            else:
                print("Invalid choice")
                
        except ValueError:
            print("Please enter a number")
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            
    # Cleanup
    await system.event_bus.stop()
    for agent in system.agents.values():
        await agent.cleanup()
    
    # Close LLM client
    await system.llm_client.__aexit__(None, None, None)
        
    print("\nDemo completed!")


async def main():
    """Main entry point"""
    await run_demo()


if __name__ == "__main__":
    asyncio.run(main())