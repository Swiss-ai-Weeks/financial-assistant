"""
The three modules of a TGN, as in the paper and the PyTorch
Geometric reference example: memory, temporal attention
embedding, link predictor.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn
from torch_geometric.nn import TGNMemory, TransformerConv
from torch_geometric.nn.models.tgn import IdentityMessage, LastAggregator, LastNeighborLoader


@dataclass(frozen=True)
class Hyperparameters:
    memory_dim: int = 100
    time_dim: int = 100
    embedding_dim: int = 100
    neighbours: int = 10
    batch_size: int = 200
    learning_rate: float = 1e-4
    epochs: int = 20


class GraphAttentionEmbedding(nn.Module):
    """
    A node's embedding at time t from its memory and its last
    `neighbours` interactions, each described by its message
    and how long ago it happened.
    """

    def __init__(self, in_channels: int, out_channels: int, msg_dim: int, time_enc: nn.Module):
        super().__init__()
        self.time_enc = time_enc
        edge_dim = msg_dim + time_enc.out_channels
        self.conv = TransformerConv(in_channels, out_channels // 2, heads=2, dropout=0.1, edge_dim=edge_dim)

    def forward(self, x, last_update, edge_index, t, msg):
        rel_t = (last_update[edge_index[0]] - t).to(x.dtype)
        edge_attr = torch.cat([self.time_enc(rel_t), msg], dim=-1)

        return self.conv(x, edge_index, edge_attr)


class LinkPredictor(nn.Module):
    def __init__(self, in_channels: int):
        super().__init__()
        self.lin_src = nn.Linear(in_channels, in_channels)
        self.lin_dst = nn.Linear(in_channels, in_channels)
        self.lin_final = nn.Linear(in_channels, 1)

    def forward(self, z_src, z_dst):
        h = self.lin_src(z_src) + self.lin_dst(z_dst)

        return self.lin_final(h.relu())


class TemporalGraphNetwork(nn.Module):
    """
    Memory, embedding and predictor together, with the
    neighbour loader they share. `assoc` maps global node ids
    to rows of the current batch, as in the reference example.
    """

    def __init__(self, num_nodes: int, msg_dim: int, hp: Hyperparameters, device: torch.device):
        super().__init__()
        self.hp = hp
        self.num_nodes = num_nodes
        self.device = device

        self.memory = TGNMemory(
            num_nodes,
            msg_dim,
            hp.memory_dim,
            hp.time_dim,
            message_module=IdentityMessage(msg_dim, hp.memory_dim, hp.time_dim),
            aggregator_module=LastAggregator(),
        ).to(device)

        self.gnn = GraphAttentionEmbedding(hp.memory_dim, hp.embedding_dim, msg_dim, self.memory.time_enc).to(device)
        self.link_pred = LinkPredictor(hp.embedding_dim).to(device)

        self.neighbor_loader = LastNeighborLoader(num_nodes, size=hp.neighbours, device=device)
        self.assoc = torch.empty(num_nodes, dtype=torch.long, device=device)

    def parameters_to_train(self):
        return set(self.memory.parameters()) | set(self.gnn.parameters()) | set(self.link_pred.parameters())

    def reset(self) -> None:
        """Forget everything: the start of an epoch, or of a scoring pass."""

        self.memory.reset_state()
        self.neighbor_loader.reset_state()

    def embed(self, n_id: torch.Tensor, data_t: torch.Tensor, data_msg: torch.Tensor):
        """
        Embeddings of the nodes in `n_id` and their sampled
        neighbours, from the current memory. Returns the
        embeddings and the node ids they belong to (the
        `assoc` map is updated for the caller).
        """

        n_id, edge_index, e_id = self.neighbor_loader(n_id)
        self.assoc[n_id] = torch.arange(n_id.size(0), device=self.device)

        z, last_update = self.memory(n_id)
        z = self.gnn(z, last_update, edge_index, data_t[e_id].to(self.device), data_msg[e_id].to(self.device))

        return z, n_id

    def observe(self, src, dst, t, msg) -> None:
        """The batch happened: update memory and neighbours."""

        self.memory.update_state(src, dst, t, msg)
        self.neighbor_loader.insert(src, dst)

    def snapshot(self) -> dict:
        return {
            "memory": self.memory.state_dict(),
            "gnn": self.gnn.state_dict(),
            "link_pred": self.link_pred.state_dict(),
            "hp": self.hp.__dict__,
            "num_nodes": self.num_nodes,
        }

    def load_snapshot(self, snapshot: dict) -> None:
        self.memory.load_state_dict(snapshot["memory"])
        self.gnn.load_state_dict(snapshot["gnn"])
        self.link_pred.load_state_dict(snapshot["link_pred"])


def pick_device(wanted: str = "auto") -> torch.device:
    if wanted != "auto":
        return torch.device(wanted)

    if torch.cuda.is_available():
        free = [torch.cuda.mem_get_info(i)[0] for i in range(torch.cuda.device_count())]
        return torch.device(f"cuda:{free.index(max(free))}")

    return torch.device("cpu")
