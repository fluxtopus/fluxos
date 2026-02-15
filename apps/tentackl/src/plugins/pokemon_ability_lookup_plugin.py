"""Pokemon Ability Lookup Plugin

Fetches Pokemon that have specific abilities from PokeAPI.
Handles dynamic iteration over abilities discovered at runtime.
"""

import httpx
from typing import Dict, Any, List
import structlog

logger = structlog.get_logger(__name__)


async def execute(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch all Pokemon that have any of the given abilities.

    Args:
        inputs: {
            "abilities": ["overgrow", "blaze", ...],  # List of ability names
            "allow_hosts": ["pokeapi.co"]  # Security: allowed hosts
        }

    Returns:
        {
            "pokemon": ["bulbasaur", "ivysaur", ...],  # Deduplicated list
            "ability_count": 3,  # Number of abilities processed
            "pokemon_count": 50  # Total unique Pokemon found
        }
    """
    abilities = inputs.get("abilities", [])
    allow_hosts = inputs.get("allow_hosts", [])

    if not abilities:
        logger.warning("No abilities provided to pokemon_ability_lookup plugin")
        return {"pokemon": [], "ability_count": 0, "pokemon_count": 0}

    if not isinstance(abilities, list):
        abilities = [abilities]

    # Deduplicate abilities
    unique_abilities = list(set(abilities))
    all_pokemon = set()

    async with httpx.AsyncClient(timeout=30.0) as client:
        for ability in unique_abilities:
            try:
                url = f"https://pokeapi.co/api/v2/ability/{ability}"

                # Security check
                if allow_hosts and not any(host in url for host in allow_hosts):
                    logger.warning("Host not in allow_hosts", url=url, allow_hosts=allow_hosts)
                    continue

                logger.info("Fetching Pokemon with ability", ability=ability, url=url)
                response = await client.get(url)
                response.raise_for_status()

                data = response.json()
                pokemon_with_ability = [
                    p["pokemon"]["name"]
                    for p in data.get("pokemon", [])
                ]

                logger.info("Found Pokemon with ability",
                           ability=ability,
                           count=len(pokemon_with_ability))

                all_pokemon.update(pokemon_with_ability)

            except httpx.HTTPError as e:
                logger.error("HTTP error fetching ability",
                            ability=ability,
                            error=str(e))
            except Exception as e:
                logger.error("Error processing ability",
                            ability=ability,
                            error=str(e))

    pokemon_list = sorted(list(all_pokemon))

    return {
        "pokemon": pokemon_list,
        "ability_count": len(unique_abilities),
        "pokemon_count": len(pokemon_list)
    }


# Plugin metadata
PLUGIN_CONFIG = {
    "name": "pokemon_ability_lookup",
    "description": "Fetch all Pokemon that have any of the specified abilities from PokeAPI",
    "category": "api",
    "inputs_schema": {
        "type": "object",
        "properties": {
            "abilities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of Pokemon ability names to lookup"
            },
            "allow_hosts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Allowed API hosts for security",
                "default": ["pokeapi.co"]
            }
        },
        "required": ["abilities"]
    },
    "outputs_schema": {
        "type": "object",
        "properties": {
            "pokemon": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Deduplicated list of Pokemon names"
            },
            "ability_count": {
                "type": "integer",
                "description": "Number of unique abilities processed"
            },
            "pokemon_count": {
                "type": "integer",
                "description": "Total number of unique Pokemon found"
            }
        }
    }
}
