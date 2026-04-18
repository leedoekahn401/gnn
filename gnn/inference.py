"""
GNN Inference Engine for GraphGuard.

Loads a trained FraudGNNModel checkpoint and provides a predict() method
that takes a Neo4j subgraph and returns a fraud probability for the target node.
"""

import torch
import torch.nn.functional as F
import numpy as np
from sklearn.preprocessing import StandardScaler

from gnn.model import FraudGNNModel


class FraudInferenceEngine:
    """
    Wraps the trained GNN model for real-time fraud inference.

    Usage:
        engine = FraudInferenceEngine("gnn/checkpoints/fraud_gnn_model_v1.pth")
        fraud_prob = engine.predict(subgraph_dict, target_node_id)
    """

    def __init__(self, checkpoint_path: str, num_features: int = 2, hidden_channels: int = 16,
                 num_classes: int = 2, edge_dim: int = 1):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = FraudGNNModel(
            num_features=num_features,
            hidden_channels=hidden_channels,
            num_classes=num_classes,
            edge_dim=edge_dim,
        ).to(self.device)

        # Load checkpoint
        state_dict = torch.load(checkpoint_path, map_location=self.device, weights_only=True)
        self.model.load_state_dict(state_dict)
        self.model.eval()

        self.scaler = StandardScaler()

    def predict(self, subgraph: dict, target_node_id: str) -> float:
        """
        Run inference on a subgraph and return fraud probability for the target node.

        Args:
            subgraph: dict with keys:
                - "nodes": list of {"id": str, "balance": float}
                - "edges": list of {"source": str, "target": str, "amount": float}
            target_node_id: The hashed user ID to score.

        Returns:
            float: Probability that the target node is fraudulent (0.0 - 1.0).
        """
        nodes = subgraph["nodes"]
        edges = subgraph["edges"]

        if not nodes or not edges:
            return 0.0

        # Build node ID -> index mapping
        node_ids = [n["id"] for n in nodes]
        node_to_idx = {nid: idx for idx, nid in enumerate(node_ids)}

        # Find target node index
        if target_node_id not in node_to_idx:
            return 0.0
        target_idx = node_to_idx[target_node_id]

        # Build node features: [1.0, scaled_balance]
        balances = np.array([n.get("balance", 0.0) for n in nodes], dtype=np.float32).reshape(-1, 1)
        if len(balances) > 1:
            scaled_balances = self.scaler.fit_transform(balances)
        else:
            scaled_balances = np.zeros_like(balances)

        x = np.hstack((np.ones((len(nodes), 1), dtype=np.float32), scaled_balances))
        x_tensor = torch.tensor(x, dtype=torch.float).to(self.device)

        # Build edge index and edge attributes
        sources = []
        targets = []
        amounts = []
        for e in edges:
            src_idx = node_to_idx.get(e["source"])
            tgt_idx = node_to_idx.get(e["target"])
            if src_idx is not None and tgt_idx is not None:
                sources.append(src_idx)
                targets.append(tgt_idx)
                amounts.append(e.get("amount", 0.0))

        if not sources:
            return 0.0

        edge_index = torch.tensor([sources, targets], dtype=torch.long).to(self.device)
        edge_amounts = np.array(amounts, dtype=np.float32).reshape(-1, 1)
        if len(edge_amounts) > 1:
            edge_attr = torch.tensor(
                self.scaler.fit_transform(edge_amounts), dtype=torch.float
            ).to(self.device)
        else:
            edge_attr = torch.zeros((len(edge_amounts), 1), dtype=torch.float).to(self.device)

        # Run inference
        with torch.no_grad():
            out = self.model(x_tensor, edge_index, edge_attr)
            probs = torch.exp(out)  # Convert log_softmax to probabilities
            fraud_prob = probs[target_idx, 1].item()  # Class 1 = fraud

        return fraud_prob
