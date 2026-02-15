import pytest
import asyncio
from src.agents.base import AgentMessage
from src.agents.message_broker import MessageBroker


class TestMessageBroker:
    
    @pytest.fixture
    def broker(self):
        return MessageBroker()
    
    @pytest.fixture
    def sample_message(self):
        return AgentMessage(
            sender_id="agent1",
            recipient_id="agent2",
            content={"data": "test"},
            message_type="test"
        )
    
    @pytest.mark.asyncio
    async def test_start_stop_broker(self, broker):
        await broker.start()
        assert broker._running is True
        assert broker._task is not None
        
        await broker.stop()
        assert broker._running is False
        assert broker._task.done()
    
    @pytest.mark.asyncio
    async def test_publish_message(self, broker, sample_message):
        await broker.start()
        
        try:
            await broker.publish(sample_message)
            assert broker._message_queue.qsize() == 1
        finally:
            await broker.stop()
    
    @pytest.mark.asyncio
    async def test_subscribe_and_receive(self, broker, sample_message):
        received_messages = []
        
        async def callback(msg):
            received_messages.append(msg)
        
        await broker.start()
        
        try:
            # Register agent and subscribe
            broker.register_agent("agent2", "topic2")
            broker.subscribe("topic2", callback)
            
            # Publish message
            await broker.publish(sample_message)
            
            # Wait for processing
            await asyncio.sleep(0.1)
            
            assert len(received_messages) == 1
            assert received_messages[0] == sample_message
        finally:
            await broker.stop()
    
    @pytest.mark.asyncio
    async def test_broadcast_message(self, broker):
        received = {"topic1": [], "topic2": []}
        
        async def callback1(msg):
            received["topic1"].append(msg)
        
        async def callback2(msg):
            received["topic2"].append(msg)
        
        await broker.start()
        
        try:
            # Subscribe to multiple topics
            broker.subscribe("topic1", callback1)
            broker.subscribe("topic2", callback2)
            
            # Broadcast message (no recipient)
            broadcast_msg = AgentMessage(
                sender_id="broadcaster",
                content={"broadcast": True}
            )
            
            await broker.publish(broadcast_msg)
            await asyncio.sleep(0.1)
            
            # Both topics should receive the message
            assert len(received["topic1"]) == 1
            assert len(received["topic2"]) == 1
        finally:
            await broker.stop()
    
    def test_unsubscribe(self, broker):
        def callback():
            pass
        
        broker.subscribe("topic", callback)
        assert callback in broker._subscribers["topic"]
        
        broker.unsubscribe("topic", callback)
        assert callback not in broker._subscribers["topic"]
    
    @pytest.mark.asyncio
    async def test_sync_callback(self, broker):
        received = []
        
        def sync_callback(msg):
            received.append(msg)
        
        await broker.start()
        
        try:
            broker.register_agent("agent1", "topic1")
            broker.subscribe("topic1", sync_callback)
            
            message = AgentMessage(
                sender_id="sender",
                recipient_id="agent1",
                content={"sync": True}
            )
            
            await broker.publish(message)
            await asyncio.sleep(0.1)
            
            assert len(received) == 1
        finally:
            await broker.stop()
    
    @pytest.mark.asyncio
    async def test_error_in_callback(self, broker, sample_message):
        async def failing_callback(msg):
            raise Exception("Callback error")
        
        async def working_callback(msg):
            pass
        
        await broker.start()
        
        try:
            broker.register_agent("agent2", "topic")
            broker.subscribe("topic", failing_callback)
            broker.subscribe("topic", working_callback)
            
            # Should not raise exception
            await broker.publish(sample_message)
            await asyncio.sleep(0.1)
            
        finally:
            await broker.stop()