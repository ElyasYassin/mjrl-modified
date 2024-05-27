import torch
import torch.nn as nn
import numpy as np
from torch.utils.tensorboard import SummaryWriter

class FCNetwork(nn.Module):
    def __init__(self, obs_dim, act_dim,
                 hidden_sizes=(64,64),
                 nonlinearity='tanh',   # either 'tanh' or 'relu'
                 in_shift=None,
                 in_scale=None,
                 out_shift=None,
                 out_scale=None,
                 log_dir='runs/activations'):
        super(FCNetwork, self).__init__()

        self.obs_dim = obs_dim
        self.act_dim = act_dim
        assert type(hidden_sizes) == tuple
        self.layer_sizes = (obs_dim,) + hidden_sizes + (act_dim,)
        self.set_transformations(in_shift, in_scale, out_shift, out_scale)

        self.fc_layers = nn.ModuleList([nn.Linear(self.layer_sizes[i], self.layer_sizes[i+1])
                                        for i in range(len(self.layer_sizes) - 1)])
        self.nonlinearity = torch.relu if nonlinearity == 'relu' else torch.tanh
        
        self.activations = {}
        self.writer = SummaryWriter(log_dir)

    def set_transformations(self, in_shift=None, in_scale=None, out_shift=None, out_scale=None):
        self.transformations = dict(in_shift=in_shift,
                                    in_scale=in_scale,
                                    out_shift=out_shift,
                                    out_scale=out_scale)
        self.in_shift = torch.from_numpy(np.float32(in_shift)) if in_shift is not None else torch.zeros(self.obs_dim)
        self.in_scale = torch.from_numpy(np.float32(in_scale)) if in_scale is not None else torch.ones(self.obs_dim)
        self.out_shift = torch.from_numpy(np.float32(out_shift)) if out_shift is not None else torch.zeros(self.act_dim)
        self.out_scale = torch.from_numpy(np.float32(out_scale)) if out_scale is not None else torch.ones(self.act_dim)

    def forward(self, x):
        if x.is_cuda:
            out = x.to('cpu')
        else:
            out = x
        out = (out - self.in_shift) / (self.in_scale + 1e-8)
        for i in range(len(self.fc_layers) - 1):
            out = self.fc_layers[i](out)
            out = self.nonlinearity(out)
        out = self.fc_layers[-1](out)
        out = out * self.out_scale + self.out_shift
        return out

    def hook_fn(self, layer_name):
        def hook(module, input, output):
            self.activations[layer_name] = output.detach().cpu().numpy()
            self.writer.add_histogram(f'Activations/{layer_name}', output)
        return hook

    def register_hooks(self):
        for i, layer in enumerate(self.fc_layers):
            layer.register_forward_hook(self.hook_fn(f'fc_layer_{i}'))

    def close_writer(self):
        self.writer.close()

    def to(self, device):
        self.device = device
        # change the transforms to the appropriate device
        self.in_shift = self.in_shift.to(device)
        self.in_scale = self.in_scale.to(device)
        self.out_shift = self.out_shift.to(device)
        self.out_scale = self.out_scale.to(device)
        # move all other trainable parameters to device
        super().to(device) 


class FCNetworkWithBatchNorm(nn.Module):
    def __init__(self, obs_dim, act_dim,
                 hidden_sizes=(64,64),
                 nonlinearity='relu',   # either 'tanh' or 'relu'
                 dropout=0,           # probability to dropout activations (0 means no dropout)
                 log_dir='runs/activations_with_batchnorm',
                 *args, **kwargs):
        super(FCNetworkWithBatchNorm, self).__init__()

        self.obs_dim = obs_dim
        self.act_dim = act_dim
        assert type(hidden_sizes) == tuple
        self.layer_sizes = (obs_dim, ) + hidden_sizes + (act_dim, )
        self.device = 'cpu'

        # hidden layers
        self.fc_layers = nn.ModuleList([nn.Linear(self.layer_sizes[i], self.layer_sizes[i+1]) \
                         for i in range(len(self.layer_sizes) - 1)])
        self.nonlinearity = torch.relu if nonlinearity == 'relu' else torch.tanh
        self.input_batchnorm = nn.BatchNorm1d(num_features=obs_dim)
        self.dropout = nn.Dropout(dropout)
        
        self.activations = {}
        self.writer = SummaryWriter(log_dir)

    def forward(self, x):
        out = x.to(self.device)
        out = self.input_batchnorm(out)
        for i in range(len(self.fc_layers) - 1):
            out = self.fc_layers[i](out)
            out = self.dropout(out)
            out = self.nonlinearity(out)
        out = self.fc_layers[-1](out)
        return out

    def hook_fn(self, layer_name):
        def hook(module, input, output):
            self.activations[layer_name] = output.detach().cpu().numpy()
            self.writer.add_histogram(f'Activations/{layer_name}', output)
        return hook

    def register_hooks(self):
        for i, layer in enumerate(self.fc_layers):
            layer.register_forward_hook(self.hook_fn(f'fc_layer_{i}'))

    def close_writer(self):
        self.writer.close()

    def to(self, device):
        self.device = device
        super().to(device)

    def set_transformations(self, *args, **kwargs):
        pass

