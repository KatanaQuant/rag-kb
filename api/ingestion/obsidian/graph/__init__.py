"""Obsidian Graph Components

POODR Phase 2.4: God Class Decomposition

Specialized extractors and query helpers for knowledge graph building:
- WikilinkExtractor: Extract wikilinks and build edges
- TagExtractor: Extract tags and build tag nodes
- HeaderExtractor: Extract headers and build hierarchy
- GraphQuery: Graph traversal and query operations

These components are composed by ObsidianGraphBuilder (orchestrator pattern).
"""

from ingestion.obsidian.graph.wikilink_extractor import WikilinkExtractor
from ingestion.obsidian.graph.tag_extractor import TagExtractor
from ingestion.obsidian.graph.header_extractor import HeaderExtractor
from ingestion.obsidian.graph.graph_query import GraphQuery

__all__ = [
    'WikilinkExtractor',
    'TagExtractor',
    'HeaderExtractor',
    'GraphQuery',
]
