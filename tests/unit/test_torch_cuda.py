"""Smoke test verifying PyTorch CUDA availability and basic tensor operations on GPU."""

import pytest
import torch


def test_torch_cuda_functional() -> None:
    """Verify that PyTorch detects CUDA and can execute tensor operations on GPU."""
    assert torch.cuda.is_available(), "CUDA must be available in .venv for GPU acceleration"
    device = torch.device("cuda:0")
    device_name = torch.cuda.get_device_name(0)
    assert "GeForce" in device_name or "RTX" in device_name or "NVIDIA" in device_name

    x = torch.randn(10, 64, device=device)
    linear = torch.nn.Linear(64, 46).to(device)
    y = linear(x)
    assert y.shape == (10, 46)
    assert y.is_cuda
