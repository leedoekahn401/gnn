import sys
import os
import torch
import torch.nn.functional as F

# Ensure backend module can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.gnn.dataset import FraudGraphDataset
from backend.gnn.model import GraphSAGEModel

def train():
    print("Initializing dataset from Neo4j...")
    dataset = FraudGraphDataset()
    try:
        data = dataset.load_data()
    except Exception as e:
        print(f"Error loading data: {e}")
        return
    finally:
        dataset.close()
        
    print(f"Loaded graph: {data.num_nodes} nodes, {data.num_edges} edges")
    print(f"Train nodes: {data.train_mask.sum().item()}, Val nodes: {data.val_mask.sum().item()}, Test nodes: {data.test_mask.sum().item()}")

    # Number of features: we used 2 (ones + scaled balance)
    num_features = data.num_node_features
    # Classes: 2 (0 = normal, 1 = fraud)
    num_classes = 2
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = GraphSAGEModel(num_features, hidden_channels=16, num_classes=num_classes).to(device)
    data = data.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=5e-4)

    def train_step():
        model.train()
        optimizer.zero_grad()
        out = model(data.x, data.edge_index)
        loss = F.nll_loss(out[data.train_mask], data.y[data.train_mask])
        loss.backward()
        optimizer.step()
        return loss.item()

    @torch.no_grad()
    def test_step():
        model.eval()
        out = model(data.x, data.edge_index)
        pred = out.argmax(dim=1)
        
        accs = []
        for mask in [data.train_mask, data.val_mask, data.test_mask]:
            correct = pred[mask] == data.y[mask]
            accs.append(int(correct.sum()) / int(mask.sum()))
        return accs

    print("Starting training loop...")
    epochs = 100
    for epoch in range(1, epochs + 1):
        loss = train_step()
        if epoch % 10 == 0:
            train_acc, val_acc, test_acc = test_step()
            print(f'Epoch: {epoch:03d}, Loss: {loss:.4f}, Train: {train_acc:.4f}, Val: {val_acc:.4f}, Test: {test_acc:.4f}')

    # Save model weights
    model_path = os.path.join(os.path.dirname(__file__), "fraud_gnn_model.pth")
    torch.save(model.state_dict(), model_path)
    print(f"Model saved to {model_path}")

if __name__ == '__main__':
    train()
