import torch
import torch.nn.functional as F
from torch_geometric.nn import GATConv

class FraudGNNModel(torch.nn.Module):
    def __init__(self, num_features, hidden_channels, num_classes, edge_dim=1):
        super(FraudGNNModel, self).__init__()
        # GATConv supports edge attributes natively via edge_dim
        self.conv1 = GATConv(num_features, hidden_channels, edge_dim=edge_dim)
        self.conv2 = GATConv(hidden_channels, num_classes, edge_dim=edge_dim)

    def forward(self, x, edge_index, edge_attr):
        # Pass edge_attr through the convolutional layers
        x = self.conv1(x, edge_index, edge_attr=edge_attr)
        x = F.relu(x)
        x = F.dropout(x, p=0.5, training=self.training)
        
        x = self.conv2(x, edge_index, edge_attr=edge_attr)
        
        # Log softmax for classification
        return F.log_softmax(x, dim=1)