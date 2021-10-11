import torch
import random
import numpy as np
import networkx as nx
import matplotlib.pyplot as plt
from types import MethodType
from typing import Optional, Callable
from torch_geometric.utils import k_hop_subgraph

from ..synthetic_dataset import ShapeGraph
from graphxai.utils.nx_conversion import khop_subgraph_nx
from graphxai import Explanation
from ..utils.shapes import house

class BAShapes(ShapeGraph):
    '''
    BA Shapes dataset with keyword arguments for different planting, 
        insertion, labeling, and feature generation methods

    ..note:: Flag and circle shapes not yet implemented

    Args:
        num_hops (int): Number of hops for each node's enclosing 
            subgraph. Should correspond to number of graph convolutional
            layers in GNN. 
        n (int): For global planting method, corresponds to the total number of 
            nodes in graph. If using local planting method, corresponds to the 
            starting number of nodes in graph.
        m (int): Number of edges per node in graph.
        num_shapes (int): Number of shapes for given planting strategy.
            If planting strategy is global, total number of shapes in
            the graph. If planting strategy is local, number of shapes
            per num_hops - hop neighborhood of each node.
        shape (str, optional): Type of shape to be inserted into graph.
            Options are `'house'`, `'flag'`, and `'circle'`. 
            (:default: :obj:`'house'`)
        insert_method (str, optional): Type of insertion strategy for 
            each motif. Options are `'plant'` or `'staple'`.
            (:default: :obj:`'plant'`)
        plant_method (str, optional): How to decide where shapes are 
            planted. 'global' method chooses random nodes from entire 
            graph. 'local' method enforces a lower bound on number of 
            shapes in the (num_hops)-hop neighborhood of each node. 
            'neighborhood upper bound' enforces an upper-bound on the 
            number of shapes per num_hops-hop neighborhood.
            (:default: :obj:`'global'`)
        feature_method (str, optional): How to generate node features.
            Options are `'network stats'` (features are network statistics),
            `'gaussian'` (features are random gaussians), and 
            `'onehot'` (features are random one-hot vectors) 
            (:default: :obj:`'network stats'`)
        labeling_rule (str, optional): Rule of how to label the nodes.
            Options are `'feature'` (only label based on feature attributes), 
            `'edge` (only label based on edge structure), 
            `'edge and feature'` (label based on both feature attributes
            and edge structure). (:default: :obj:`'edge and feature'`)

        kwargs: Additional arguments
            shape_upper_bound (int, Optional): Number of maximum shapes
                to add per num_hops-hop neighborhood in the 'neighborhood
                upper bound' planting policy.
    '''

    def __init__(self, 
        num_hops: int, 
        n: int, 
        m: int, 
        num_shapes: int, 
        shape: Optional[str] = 'house',
        seed: Optional[int] = None,
        insert_method: Optional[str] = 'plant',
        plant_method: Optional[str] = 'global',
        feature_method: Optional[str] = 'network stats',
        labeling_method: Optional[str] = 'edge and feature',
        **kwargs):

        self.n = n
        self.m = m
        self.seed = seed

        self.feature_method = feature_method.lower()
        self.labeling_method = labeling_method.lower()
        if self.labeling_method == 'feature and edge':
            self.labeling_method = 'edge and feature'

        if plant_method == 'neighborhood upper bound' and num_shapes is None:
            num_shapes = n # Set to maximum if num_houses left at None

        if shape.lower() == 'house':
            insert_shape = house
        elif shape.lower() == 'flag':
            pass
        elif shape.lower() == 'circle':
            pass

        super().__init__(
            name='BAHouses', 
            num_hops=num_hops,
            num_shapes = num_shapes,
            insert_method = insert_method,
            plant_method = plant_method,
            insertion_shape = insert_shape,
            **kwargs
        )

    def init_graph(self):
        '''
        Returns a Barabasi-Albert graph with desired parameters
        '''
        self.G = nx.barabasi_albert_graph(self.n, self.m, seed = self.seed)

    def feature_generator(self):
        '''
        Returns function to generate features for one node_idx
        '''
        if self.feature_method == 'network stats':
            deg_cent = nx.degree_centrality(self.G)
            def get_feature(node_idx):
                return torch.tensor([self.G.degree[node_idx], 
                    nx.clustering(self.G, node_idx), 
                    deg_cent[node_idx]]).float()

        elif self.feature_method == 'gaussian':
            def get_feature(node_idx):
                # Random random Gaussian feature vector:
                return torch.normal(mean=0, std=1.0, size = (3,))

        elif self.feature_method == 'onehot':
            def get_feature(node_idx):
                # Random one-hot feature vector:
                feature = torch.zeros(3)
                feature[random.choice(range(3))] = 1
                return feature
        else:
            raise NotImplementedError()

        return get_feature

    def labeling_rule(self):
        '''
        Labeling rule for each node
        '''

        avg_ccs = np.mean([self.G.nodes[i]['x'][1] for i in self.G.nodes])
        
        def get_label(node_idx):
            # Count number of houses in k-hop neighborhood
            # subset, _, _, _ = k_hop_subgraph(node_idx, self.num_hops, self.graph.edge_index)
            # shapes = self.graph.shape[subset]
            # num_houses = (torch.unique(shapes) > 0).nonzero(as_tuple=True)[0]
            khop_edges = nx.bfs_edges(self.G, node_idx, depth_limit = self.num_hops)
            nodes_in_khop = set(np.unique(list(khop_edges))) - set([node_idx])
            num_unique_houses = len(np.unique([self.G.nodes[ni]['shape'] for ni in nodes_in_khop if self.G.nodes[ni]['shape'] > 0 ]))
            # Enfore logical condition:
            return torch.tensor(int(num_unique_houses == 1 and self.G.nodes[node_idx]['x'][0] > 1), dtype=torch.long)


        if self.labeling_method == 'edge':
            # Label based soley on edge structure
            # Based on number of houses in neighborhood
            def get_label(node_idx):
                nodes_in_khop = khop_subgraph_nx(node_idx, self.num_hops, self.G)
                num_unique_houses = len(np.unique([self.G.nodes[ni]['shape'] \
                    for ni in nodes_in_khop if self.G.nodes[ni]['shape'] > 0 ]))
                return torch.tensor(int(num_unique_houses == 1), dtype=torch.long)

        elif self.labeling_method == 'feature':
            # Label based solely on node features
            # Based on if feature[1] > median of all nodes
            max_node = len(list(self.G.nodes))
            node_attr = nx.get_node_attributes(self.G, 'x')
            x1 = [node_attr[i][1] for i in range(max_node)]
            med1 = np.median(x1)
            def get_label(node_idx):
                return torch(int(x1[node_idx] > med1), dtype=torch.long)

        elif self.labeling_method == 'edge and feature':
            # Calculate median (as for feature):
            max_node = len(list(self.G.nodes))
            node_attr = nx.get_node_attributes(self.G, 'x')
            x1 = [node_attr[i][1] for i in range(max_node)]
            med1 = np.median(x1)

            def get_label(node_idx):
                nodes_in_khop = khop_subgraph_nx(node_idx, self.num_hops, self.G)
                num_unique_houses = len(np.unique([self.G.nodes[ni]['shape'] \
                    for ni in nodes_in_khop if self.G.nodes[ni]['shape'] > 0 ]))
                return torch.tensor(int(num_unique_houses == 1 and x1[node_idx] > med1), dtype=torch.long)

        else:
            raise NotImplementedError() 
                
        return get_label

    def explanation_generator(self):
        def gen(node_idx):
            return None
        return gen

    def visualize(self):
        ylist = self.graph.y.tolist()
        y = [ylist[i] for i in self.G.nodes]

        pos = nx.kamada_kawai_layout(self.G)
        _, ax = plt.subplots()
        nx.draw(self.G, pos, node_color = y, ax=ax)
        ax.set_title('BA Houses')
        plt.tight_layout()
        plt.show()

if __name__ == '__main__':
    class Hyperparameters:
        num_hops = 1
        n = 5000
        m = 1
        num_shapes = None
        plant_method = 'neighborhood upper bound'
        shape_upper_bound = 1
        labeling_method = 'edge'

    hyp = Hyperparameters
    bah = BAShapes(**args, feature_method = 'gaussian')
    
    args = {key:value for key, value in hyp.__dict__.items() if not key.startswith('__') and not callable(value)}

    bah.visualize()