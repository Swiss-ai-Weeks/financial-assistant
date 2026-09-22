"""
A temporal graph network over the news graph.

Rossi et al., "Temporal Graph Networks for Deep Learning on
Dynamic Graphs" (2020): every node keeps a memory updated by
the events it takes part in, an attention layer over recent
neighbours turns memory into an embedding at time t, and the
model is trained to tell real future edges from sampled ones.

Here the events are the graph's edges in publication order
(security -> entity / event / event type). Trained, the model
gives every observed edge a probability it was expected, and
every security a memory vector that moves as its news does.

    dataset   the store's edges as a TemporalData stream
    model     memory + attention embedding + link predictor
    train     chronological split, AP/AUC, checkpoint
    score     surprise per edge, per security per day; drift;
              the expected edges of next week
"""
