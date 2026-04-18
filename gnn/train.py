import sys
import os
import argparse
import torch
import torch.nn.functional as F
import numpy as np
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

# Ensure backend module can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.gnn.dataset import FraudGraphDataset
from backend.gnn.model import FraudGNNModel  

def parse_args():
    parser = argparse.ArgumentParser(description="Train Fraud Detection GNN")
    parser.add_argument('--save_version', type=str, default='v1', 
                        help='Version name to save the trained model (e.g., v1, v2.1, experiment_5)')
    parser.add_argument('--load_version', type=str, default=None, 
                        help='Version name to load and resume training from. If None, starts from scratch.')
    parser.add_argument('--epochs', type=int, default=100, 
                        help='Number of epochs to train')
    return parser.parse_args()

def train(args):
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

    num_features = data.num_node_features
    num_classes = 2
    edge_dim = data.edge_attr.shape[1] if data.edge_attr is not None else 1
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = FraudGNNModel(num_features, hidden_channels=16, num_classes=num_classes, edge_dim=edge_dim).to(device)
    data = data.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=5e-4)

    # --- VERSIONING AND LOADING LOGIC ---
    checkpoints_dir = os.path.join(os.path.dirname(__file__), "checkpoints")
    os.makedirs(checkpoints_dir, exist_ok=True)

    if args.load_version:
        load_path = os.path.join(checkpoints_dir, f"fraud_gnn_model_{args.load_version}.pth")
        if os.path.exists(load_path):
            model.load_state_dict(torch.load(load_path, map_location=device))
            print(f"✅ Successfully loaded model weights from version: '{args.load_version}'")
            print(f"Resuming training for {args.epochs} epochs...")
        else:
            print(f"⚠️ Warning: Model version '{args.load_version}' not found at {load_path}. Starting fresh.")

    # Calculate Class Weights for Imbalanced Data
    y_train = data.y[data.train_mask]
    num_normal = (y_train == 0).sum().item()
    num_fraud = (y_train == 1).sum().item()
    
    weight_normal = 1.0
    weight_fraud = (num_normal / num_fraud) if num_fraud > 0 else 1.0
    
    class_weights = torch.tensor([weight_normal, weight_fraud], dtype=torch.float).to(device)

    def train_step():
        model.train()
        optimizer.zero_grad()
        out = model(data.x, data.edge_index, data.edge_attr)
        loss = F.nll_loss(out[data.train_mask], data.y[data.train_mask], weight=class_weights)
        loss.backward()
        optimizer.step()
        return loss.item()

    @torch.no_grad()
    def test_step():
        model.eval()
        out = model(data.x, data.edge_index, data.edge_attr)
        pred = out.argmax(dim=1)
        probs = torch.exp(out)[:, 1] 
        
        metrics = {}
        for mask_name, mask in [('train', data.train_mask), ('val', data.val_mask), ('test', data.test_mask)]:
            y_true = data.y[mask].cpu().numpy()
            y_pred = pred[mask].cpu().numpy()
            y_prob = probs[mask].cpu().numpy()
            
            try:
                roc_auc = roc_auc_score(y_true, y_prob)
            except ValueError:
                roc_auc = 0.5 
                
            metrics[mask_name] = {
                'f1': f1_score(y_true, y_pred, zero_division=0),
                'precision': precision_score(y_true, y_pred, zero_division=0),
                'recall': recall_score(y_true, y_pred, zero_division=0),
                'roc_auc': roc_auc
            }
        return metrics

    print("Starting training loop...")
    for epoch in range(1, args.epochs + 1):
        loss = train_step()
        if epoch % 10 == 0:
            metrics = test_step()
            val_m = metrics['val']
            print(f"Epoch: {epoch:03d}, Loss: {loss:.4f} | "
                  f"Val F1: {val_m['f1']:.4f}, Prec: {val_m['precision']:.4f}, "
                  f"Rec: {val_m['recall']:.4f}, AUC: {val_m['roc_auc']:.4f}")

    # --- SAVING LOGIC ---
    save_path = os.path.join(checkpoints_dir, f"fraud_gnn_model_{args.save_version}.pth")
    torch.save(model.state_dict(), save_path)
    print(f"\n💾 Model successfully saved to: {save_path}")

    # --- FINAL TEST SET EVALUATION ---
    final_metrics = test_step()
    test_m = final_metrics['test']
    print("\n" + "=" * 50)
    print("📊 FINAL TEST SET METRICS")
    print("=" * 50)
    print(f"  Precision : {test_m['precision']:.4f}")
    print(f"  Recall    : {test_m['recall']:.4f}")
    print(f"  F1 Score  : {test_m['f1']:.4f}")
    print(f"  AUC-ROC   : {test_m['roc_auc']:.4f}")
    print("=" * 50)

if __name__ == '__main__':
    args = parse_args()
    train(args)