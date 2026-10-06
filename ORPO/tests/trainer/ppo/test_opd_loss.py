import torch

from verl.trainer.ppo.core_algos import compute_opd_loss


def test_opd_loss_matches_seed_gate_and_detaches_teacher():
    log_prob = torch.tensor([[-2.0, -1.0, -0.5], [-3.0, -0.2, -1.5]], requires_grad=True)
    teacher_log_prob = torch.tensor([[-1.0, -2.0, -0.4], [-2.5, -0.1, -2.0]], requires_grad=True)
    response_mask = torch.tensor([[1.0, 1.0, 0.0], [1.0, 1.0, 1.0]])
    opd_step_mask = torch.tensor([1.0, 0.0])

    opd_loss, active_ratio, gate_mean, gate_active_ratio, teacher_gap_mean = compute_opd_loss(
        log_prob=log_prob,
        teacher_log_prob=teacher_log_prob,
        response_mask=response_mask,
        opd_step_mask=opd_step_mask,
        gate_beta=5.0,
        loss_agg_mode="token-mean",
    )

    gap = (teacher_log_prob.detach() - log_prob.detach())
    gate = torch.sigmoid(5.0 * gap)
    expected = (gate * (teacher_log_prob.detach() - log_prob) * response_mask * opd_step_mask.unsqueeze(-1)).sum()
    expected = expected / (response_mask * opd_step_mask.unsqueeze(-1)).sum()
    assert torch.allclose(opd_loss, expected)
    assert teacher_log_prob.grad is None
    opd_loss.backward()
    assert log_prob.grad is not None
    assert teacher_log_prob.grad is None
    assert active_ratio.item() == 2.0 / 6.0
    assert gate_mean.item() > 0
    assert 0.0 <= gate_active_ratio.item() <= 1.0
    assert teacher_gap_mean.ndim == 0


def test_opd_loss_zero_when_mask_empty():
    log_prob = torch.zeros(2, 3, requires_grad=True)
    teacher_log_prob = torch.ones(2, 3)
    response_mask = torch.ones(2, 3)
    opd_step_mask = torch.zeros(2)
    opd_loss, active_ratio, *_ = compute_opd_loss(
        log_prob=log_prob,
        teacher_log_prob=teacher_log_prob,
        response_mask=response_mask,
        opd_step_mask=opd_step_mask,
    )
    assert float(opd_loss) == 0.0
    assert float(active_ratio) == 0.0
    opd_loss.backward()
    assert torch.all(log_prob.grad == 0)


def test_opsd_loss_ungated_when_gate_beta_nonpositive():
    log_prob = torch.tensor([[-2.0, -1.0, -0.5]], requires_grad=True)
    teacher_log_prob = torch.tensor([[-1.0, -2.0, -0.4]], requires_grad=True)
    response_mask = torch.tensor([[1.0, 1.0, 0.0]])

    opd_loss, _, gate_mean, gate_active_ratio, _ = compute_opd_loss(
        log_prob=log_prob,
        teacher_log_prob=teacher_log_prob,
        response_mask=response_mask,
        opd_step_mask=torch.tensor([1.0]),
        gate_beta=0.0,
        loss_agg_mode="token-mean",
    )

    expected = ((teacher_log_prob.detach() - log_prob) * response_mask).sum() / response_mask.sum()
    assert torch.allclose(opd_loss, expected)
    assert float(gate_mean) == 1.0
    assert float(gate_active_ratio) == 1.0
    opd_loss.backward()
    assert log_prob.grad is not None
    assert teacher_log_prob.grad is None
