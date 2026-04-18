import torch
from torch_geometric.data import Data
from backend.db.neo4j_client import Neo4jClient
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler

class FraudGraphDataset:
    def __init__(self):
        self.client = Neo4jClient()
        self.scaler = StandardScaler()

    def load_data(self):
        # 1. Fetch nodes (Users)
        query_nodes = "MATCH (u:User) RETURN u.id AS id, u.balance AS balance, u.is_fraud AS is_fraud"
        with self.client.driver.session() as session:
            result_nodes = session.run(query_nodes)
            nodes_data = [record.data() for record in result_nodes]
            
        if not nodes_data:
            raise ValueError("No nodes found in database. Did you run the simulation?")

        df_nodes = pd.DataFrame(nodes_data)
        
        # Create mapping from user ID to integer index
        user_to_idx = {user_id: idx for idx, user_id in enumerate(df_nodes['id'])}
        
        # Node features (we'll use balance, and maybe in the future degree centrality)
        # Scale the balance
        balances = df_nodes['balance'].values.reshape(-1, 1)
        scaled_balances = self.scaler.fit_transform(balances)
        
        # Initialize x with ones and scaled balances
        # Shape: (num_nodes, 2)
        x = torch.tensor(
            np.hstack((np.ones((len(df_nodes), 1)), scaled_balances)), 
            dtype=torch.float
        )
        
        # Node labels (0 = normal, 1 = fraud)
        y = torch.tensor(df_nodes['is_fraud'].astype(int).values, dtype=torch.long)

        # 2. Fetch edges (Transactions)
        query_edges = "MATCH (s:User)-[r:TRANSACTED]->(t:User) RETURN s.id AS source, t.id AS target, r.amount AS amount"
        with self.client.driver.session() as session:
            result_edges = session.run(query_edges)
            edges_data = [record.data() for record in result_edges]

        if not edges_data:
            raise ValueError("No edges found in database.")

        df_edges = pd.DataFrame(edges_data)
        
        # Map IDs to integer indices
        source_indices = [user_to_idx[src] for src in df_edges['source']]
        target_indices = [user_to_idx[tgt] for tgt in df_edges['target']]
        
        # Edge indices
        edge_index = torch.tensor([source_indices, target_indices], dtype=torch.long)
        
        # Edge attributes (amount)
        edge_amounts = df_edges['amount'].values.reshape(-1, 1)
        edge_attr = torch.tensor(self.scaler.fit_transform(edge_amounts), dtype=torch.float)

        # 3. Create PyTorch Geometric Data object
        data = Data(x=x, edge_index=edge_index, edge_attr=edge_attr, y=y)
        
        # Split nodes into train, val, test masks
        # Since this is a simple simulation, we'll do 60/20/20 random split
        num_nodes = data.num_nodes
        indices = np.random.permutation(num_nodes)
        
        train_end = int(num_nodes * 0.6)
        val_end = int(num_nodes * 0.8)
        
        train_idx = indices[:train_end]
        val_idx = indices[train_end:val_end]
        test_idx = indices[val_end:]
        
        data.train_mask = torch.zeros(num_nodes, dtype=torch.bool)
        data.val_mask = torch.zeros(num_nodes, dtype=torch.bool)
        data.test_mask = torch.zeros(num_nodes, dtype=torch.bool)
        
        data.train_mask[train_idx] = True
        data.val_mask[val_idx] = True
        data.test_mask[test_idx] = True

        return data

    def close(self):
        self.client.close()
