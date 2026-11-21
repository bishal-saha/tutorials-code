"""Lesson 1 tests: the runaway behaves as the lesson describes."""

from runaway import SAFETY_NET, main, run_unbounded


def test_only_the_safety_net_stops_it():
    assert len(run_unbounded()) == SAFETY_NET


def test_every_step_repeats_the_same_call():
    steps = run_unbounded()
    assert len({(s.tool, s.arguments) for s in steps}) == 1


def test_each_step_costs_more_than_the_last():
    costs = [s.cost for s in run_unbounded()]
    assert all(b > a for a, b in zip(costs, costs[1:], strict=False))


def test_printed_summary(capsys):
    main()
    out = capsys.readouterr().out
    assert "25 steps, 1 distinct call" in out
    assert "nothing found" in out
