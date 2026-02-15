from src.plugins.registry import registry, PluginDefinition


def test_builtin_plugins_available():
    assert registry.get("echo") is not None
    assert registry.get("sum") is not None


def test_sum_plugin_execution():
    import asyncio

    async def run():
        res = await registry.execute("sum", {"numbers": [1, 2, 3.5]})
        assert res["sum"] == 6.5

    asyncio.run(run())

