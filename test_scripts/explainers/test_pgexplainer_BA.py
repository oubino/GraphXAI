import random
import torch

from graphxai.explainers import PGExplainer
from graphxai.explainers.utils.visualizations import visualize_subgraph_explanation
from graphxai.gnn_models.node_classification import BA_Houses, GCN, train, test


n = 300
m = 2
num_houses = 20

bah = BA_Houses(n, m)
data, inhouse = bah.get_data(num_houses, multiple_features=True)

model = GCN(64, input_feat=3, classes=2)
print(model)

optimizer = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=5e-4)
criterion = torch.nn.CrossEntropyLoss()

for epoch in range(1, 201):
    loss = train(model, optimizer, criterion, data)
    acc = test(model, data)
    print(f'Epoch: {epoch:03d}, Loss: {loss:.4f}, Test Acc: {acc:.4f}')

node_idx = random.choice(inhouse)

model.eval()
pred = model(data.x, data.edge_index)[node_idx, :].reshape(-1, 1)
print('pred shape', pred.shape)
print('GROUND TRUTH LABEL: \t {}'.format(data.y[node_idx].item()))
print('PREDICTED LABEL   : \t {}'.format(pred.argmax(dim=0).item()))

explainer = PGExplainer(model, explain_graph=False)
explainer.train_explanation_model(data)

# With true label
exp, khop_info = explainer.get_explanation_node(int(node_idx), data.x,
                                                data.edge_index, data.y)
Without true label
exp_no_label, khop_info = explainer.get_explanation_node(int(node_idx), data.x,
                                                         data.edge_index)