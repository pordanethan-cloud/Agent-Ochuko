"""
Search-Based Tree Planning Engine (LATS / Tree of Thoughts) for Agent Ochuko.
Explores multiple execution branches for complex architectural planning and multi-file edits.
"""
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ThoughtNode(BaseModel):
    node_id: int
    parent_id: Optional[int] = None
    thought: str
    score: float = 0.0
    children: List[int] = []


class TreePlanner:
    """Manages search tree exploration for multi-path decision making."""

    def __init__(self, goal: str):
        self.goal = goal
        self.nodes: Dict[int, ThoughtNode] = {}
        self.next_id = 1
        # Root node
        root = ThoughtNode(node_id=0, thought=f"Goal: {goal}", score=0.0)
        self.nodes[0] = root

    def add_child(self, parent_id: int, thought: str, score: float = 0.5) -> ThoughtNode:
        """Add candidate decision node to search tree."""
        node_id = self.next_id
        self.next_id += 1
        
        node = ThoughtNode(node_id=node_id, parent_id=parent_id, thought=thought, score=score)
        self.nodes[node_id] = node
        
        if parent_id in self.nodes:
            self.nodes[parent_id].children.append(node_id)
            
        logger.info(f"TreePlanner added candidate node {node_id} (score: {score}): {thought[:60]}")
        return node

    def get_best_path(self) -> List[ThoughtNode]:
        """Traverses nodes to select the highest-scoring candidate trajectory."""
        if not self.nodes:
            return []

        # Find best leaf node
        best_node = max(self.nodes.values(), key=lambda n: n.score)
        path = []
        curr: Optional[ThoughtNode] = best_node
        
        while curr:
            path.append(curr)
            curr = self.nodes.get(curr.parent_id) if curr.parent_id is not None else None

        path.reverse()
        return path


def create_tree_planner(goal: str) -> TreePlanner:
    return TreePlanner(goal=goal)
